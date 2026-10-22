import hashlib
import json
import logging
import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text, or_

from backend.app.config import settings
from backend.app.models.user import User
from backend.app.models.memory import ConversationMemory, SAPScenarioMemory, ConversationSummary
from backend.app.services.embedding_service import embedding_service
from backend.app.services.sap_entity_service import sap_entity_service

logger = logging.getLogger(__name__)

# Regex patterns for redacting sensitive secrets
SENSITIVE_PATTERNS = [
    (re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?([^\s'\";]+)['\"]?"), r"\1=[REDACTED_SECRET]"),
    (re.compile(r"(?i)(bearer\s+)([a-zA-Z0-9_\-\.=]+)"), r"\1[REDACTED_TOKEN]"),
    (re.compile(r"(?i)(api[_\-]?key|secret[_\-]?key|secret)\s*[:=]\s*['\"]?([^\s'\";]+)['\"]?"), r"\1=[REDACTED_SECRET]"),
    (re.compile(r"(?i)(token)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{12,})['\"]?"), r"\1=[REDACTED_TOKEN]"),
    (re.compile(r"(?i)(authorization:\s*bearer\s+)([^\s]+)"), r"\1[REDACTED_TOKEN]"),
]

# Common SAP BRIM patterns
SAP_MODULE_PATTERNS = {
    "SOM": re.compile(r"\b(SOM|Subscription Order Management|Provider Contract|Provider Order)\b", re.I),
    "CC": re.compile(r"\b(CC|Convergent Charging|Charging|Rating|Charged Items?)\b", re.I),
    "CI": re.compile(r"\b(CI|Convergent Invoicing|Billable Items?|BITs?|Billing Document|Invoicing Document)\b", re.I),
    "FI-CA": re.compile(r"\b(FI-CA|FICA|Contract Accounts?|Contract Accounts Receivable and Payable|Payment Lot|Dunning|Reconciliation Key|FIKEY)\b", re.I),
    "SD": re.compile(r"\b(Sales and Distribution|Sales Order|Billing Plan)\b", re.I),
    "S4_FINANCE": re.compile(r"\b(S/4HANA Finance|General Ledger|GL|ACDOCA|BSEG)\b", re.I),
}

TCODE_PATTERN = re.compile(r"\b([A-Z0-9_]{3,16})\b")
TABLE_PATTERN = re.compile(r"\b(DFKK[A-Z0-9_]+|BUT\d{3}|FKK[A-Z0-9_]+|ACDOCA|BSEG|BKPF|CRMD_[A-Z0-9_]+)\b", re.I)

class MemoryService:
    """
    Data-access layer and orchestration engine for persistent cross-chat memory.
    Enforces strict authenticated user isolation on every operation.
    """

    # =========================================================================
    # 1. SECURITY & DATA ACCESS LAYER (Strictly Scoped by user_id)
    # =========================================================================

    @staticmethod
    def redact_sensitive_data(text_content: str) -> str:
        """Redacts secrets, API keys, passwords, and tokens before persistence."""
        if not text_content:
            return ""
        redacted = text_content
        for pattern, replacement in SENSITIVE_PATTERNS:
            redacted = pattern.sub(replacement, redacted)
        return redacted

    @staticmethod
    def compute_content_hash(text_content: str) -> str:
        """Normalized hash for exact deduplication."""
        normalized = re.sub(r"\s+", " ", text_content.strip().lower())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def get_user_memory_enabled(self, db: Session, user_id: str) -> bool:
        """Checks if memory is enabled for the authenticated user."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        return getattr(user, "memory_enabled", True)

    def set_user_memory_enabled(self, db: Session, user_id: str, enabled: bool) -> bool:
        """Toggles memory persistence for the authenticated user."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        user.memory_enabled = enabled
        db.commit()
        db.refresh(user)
        return user.memory_enabled

    def list_memories(
        self,
        db: Session,
        user_id: str,
        memory_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[ConversationMemory], int]:
        """Paginated list of memories strictly scoped to user_id."""
        query = db.query(ConversationMemory).filter(ConversationMemory.user_id == user_id)
        if memory_type:
            query = query.filter(ConversationMemory.memory_type == memory_type)
        if status:
            query = query.filter(ConversationMemory.status == status)
        else:
            # By default exclude superseded memories
            query = query.filter(ConversationMemory.status != "superseded")

        total = query.count()
        items = query.order_by(ConversationMemory.updated_at.desc()).offset(offset).limit(limit).all()
        return items, total

    def get_memory(self, db: Session, user_id: str, memory_id: str) -> Optional[ConversationMemory]:
        """Fetch memory with strict user_id check."""
        return db.query(ConversationMemory).filter(
            ConversationMemory.id == memory_id,
            ConversationMemory.user_id == user_id
        ).first()

    def update_memory(
        self,
        db: Session,
        user_id: str,
        memory_id: str,
        summary: Optional[str] = None,
        memory_type: Optional[str] = None,
        status: Optional[str] = None,
        entities: Optional[Any] = None
    ) -> Optional[ConversationMemory]:
        """Update or correct a memory fact; verifies ownership."""
        mem = self.get_memory(db, user_id, memory_id)
        if not mem:
            return None

        if summary is not None:
            clean_summary = self.redact_sensitive_data(summary.strip())
            mem.summary = clean_summary
            mem.content_hash = self.compute_content_hash(clean_summary)
            try:
                mem.embedding = embedding_service.embed_text(clean_summary)
            except Exception as e:
                logger.warning(f"Could not compute embedding on memory update: {e}")
        if memory_type is not None:
            mem.memory_type = memory_type
        if status is not None:
            mem.status = status
        if entities is not None:
            mem.entities = json.dumps(entities) if not isinstance(entities, str) else entities

        mem.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(mem)
        return mem

    def delete_memory(self, db: Session, user_id: str, memory_id: str) -> bool:
        """Delete a single memory belonging to authenticated user."""
        mem = self.get_memory(db, user_id, memory_id)
        if not mem:
            return False
        db.delete(mem)
        db.commit()
        return True

    def delete_all_user_memories(self, db: Session, user_id: str) -> int:
        """Purges all memory records across all memory tables for this user."""
        count = 0
        c_mems = db.query(ConversationMemory).filter(ConversationMemory.user_id == user_id).all()
        count += len(c_mems)
        for m in c_mems:
            db.delete(m)

        s_mems = db.query(SAPScenarioMemory).filter(SAPScenarioMemory.user_id == user_id).all()
        count += len(s_mems)
        for s in s_mems:
            db.delete(s)

        c_sums = db.query(ConversationSummary).filter(ConversationSummary.user_id == user_id).all()
        count += len(c_sums)
        for cs in c_sums:
            db.delete(cs)

        db.commit()
        return count

    def list_scenarios(
        self,
        db: Session,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[SAPScenarioMemory], int]:
        """Paginated list of SAP scenario memories strictly scoped to user_id."""
        query = db.query(SAPScenarioMemory).filter(SAPScenarioMemory.user_id == user_id)
        if status:
            query = query.filter(SAPScenarioMemory.status == status)

        total = query.count()
        items = query.order_by(SAPScenarioMemory.updated_at.desc()).offset(offset).limit(limit).all()
        return items, total

    def get_scenario(self, db: Session, user_id: str, scenario_id: str) -> Optional[SAPScenarioMemory]:
        """Fetch scenario with strict user_id check."""
        return db.query(SAPScenarioMemory).filter(
            SAPScenarioMemory.id == scenario_id,
            SAPScenarioMemory.user_id == user_id
        ).first()

    def update_scenario(
        self,
        db: Session,
        user_id: str,
        scenario_id: str,
        updates: Dict[str, Any]
    ) -> Optional[SAPScenarioMemory]:
        """Updates an SAP scenario memory; verifies ownership."""
        scenario = self.get_scenario(db, user_id, scenario_id)
        if not scenario:
            return None

        if "scenario_title" in updates and updates["scenario_title"]:
            scenario.scenario_title = updates["scenario_title"].strip()
        if "symptoms" in updates and updates["symptoms"] is not None:
            scenario.symptoms = self.redact_sensitive_data(updates["symptoms"].strip())
        if "affected_modules" in updates:
            val = updates["affected_modules"]
            scenario.affected_modules = json.dumps(val) if not isinstance(val, str) else val
        if "status" in updates and updates["status"]:
            scenario.status = updates["status"]
        if "confirmed_findings" in updates:
            val = updates["confirmed_findings"]
            scenario.confirmed_findings = json.dumps(val) if not isinstance(val, str) else val
        if "attempted_solutions" in updates:
            val = updates["attempted_solutions"]
            scenario.attempted_solutions = json.dumps(val) if not isinstance(val, str) else val
        if "unresolved_questions" in updates:
            val = updates["unresolved_questions"]
            scenario.unresolved_questions = json.dumps(val) if not isinstance(val, str) else val

        scenario.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(scenario)
        return scenario

    def delete_scenario(self, db: Session, user_id: str, scenario_id: str) -> bool:
        """Delete an SAP scenario belonging to authenticated user."""
        scenario = self.get_scenario(db, user_id, scenario_id)
        if not scenario:
            return False
        db.delete(scenario)
        db.commit()
        return True

    # =========================================================================
    # 2. ENTITY & TERM EXTRACTION HELPERS
    # =========================================================================

    @staticmethod
    def extract_sap_entities(text_content: str) -> Dict[str, List[str]]:
        """Extracts SAP modules, T-codes, and database tables from text."""
        if not text_content:
            return {"modules": [], "tcodes": [], "tables": []}

        # Modules
        found_modules = []
        for mod, pat in SAP_MODULE_PATTERNS.items():
            if pat.search(text_content):
                found_modules.append(mod)

        # Tables
        found_tables = set()
        for m in TABLE_PATTERN.finditer(text_content):
            cand = m.group(1).upper()
            if sap_entity_service.is_known_sap_identifier(cand) or cand.startswith("DFKK") or cand.startswith("BUT") or cand in ("ACDOCA", "BSEG", "BKPF"):
                found_tables.add(cand)

        # T-codes
        found_tcodes = set()
        for m in TCODE_PATTERN.finditer(text_content):
            cand = m.group(1).upper()
            if sap_entity_service.is_known_sap_identifier(cand):
                found_tcodes.add(cand)

        return {
            "modules": list(set(found_modules)),
            "tcodes": list(found_tcodes),
            "tables": list(found_tables),
        }

    # =========================================================================
    # 3. HYBRID RETRIEVAL & CONTEXT FORMATION
    # =========================================================================

    def _cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Fast portable cosine similarity calculation."""
        if not vec_a or not vec_b:
            return 0.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return max(0.0, min(1.0, dot / (norm_a * norm_b)))

    def retrieve_relevant_memories(
        self,
        db: Session,
        user_id: str,
        query: str,
        current_chat_id: Optional[str] = None,
        top_k: int = 5,
        max_chars: int = 3500
    ) -> Dict[str, Any]:
        """
        Hybrid retrieval combining semantic similarity + keyword/entity match.
        Strictly user-filtered, bounded top-K, and formatted with security delimiters.
        """
        if not self.get_user_memory_enabled(db, user_id):
            return {
                "used_memories": [],
                "used_memory_ids": [],
                "formatted_context": "",
                "previous_context_used": False,
                "top_scenario": None
            }

        extracted = self.extract_sap_entities(query)
        all_query_terms = set(
            [m.lower() for m in extracted["modules"]] +
            [t.lower() for t in extracted["tcodes"]] +
            [tbl.lower() for tbl in extracted["tables"]] +
            [w.lower() for w in re.findall(r"\b[A-Za-z0-9_\-]{3,}\b", query)]
        )

        try:
            q_emb = embedding_service.embed_text(query)
        except Exception as e:
            logger.warning(f"Failed to embed query for memory retrieval: {e}")
            q_emb = None

        now = datetime.now(timezone.utc)

        # 1. Retrieve Candidate Conversation Memories (Active, not superseded)
        mem_candidates = (
            db.query(ConversationMemory)
            .filter(
                ConversationMemory.user_id == user_id,
                ConversationMemory.status == "active",
                ConversationMemory.superseded_by.is_(None)
            )
            .all()
        )

        scored_mems = []
        for mem in mem_candidates:
            # Semantic score
            sim = 0.0
            if q_emb and mem.embedding:
                try:
                    sim = self._cosine_similarity(q_emb, mem.embedding)
                except Exception:
                    sim = 0.0

            # Keyword / exact identifier match score
            summary_lower = mem.summary.lower()
            keyword_hits = sum(1 for term in all_query_terms if term in summary_lower)
            keyword_score = min(1.0, keyword_hits * 0.25)

            # Recency factor (newer memories slightly prioritized)
            age_days = (now - mem.updated_at.replace(tzinfo=timezone.utc)).total_seconds() / 86400.0
            recency = max(0.0, 1.0 - (age_days / 30.0))

            # Composite hybrid score (active standing preferences are always boosted)
            pref_boost = 0.45 if mem.memory_type == "preference" else 0.0
            hybrid_score = (0.50 * sim) + (0.35 * keyword_score) + (0.15 * recency) + pref_boost
            if hybrid_score > 0.25 or keyword_hits > 0 or mem.memory_type == "preference":
                scored_mems.append({
                    "score": hybrid_score,
                    "item": mem,
                    "type": "conversation_memory"
                })

        # 2. Retrieve Candidate SAP Scenario Memories
        scen_candidates = (
            db.query(SAPScenarioMemory)
            .filter(SAPScenarioMemory.user_id == user_id)
            .all()
        )

        scored_scens = []
        for scen in scen_candidates:
            sim = 0.0
            if q_emb and scen.embedding:
                try:
                    sim = self._cosine_similarity(q_emb, scen.embedding)
                except Exception:
                    sim = 0.0

            scen_text = f"{scen.scenario_title} {scen.symptoms or ''} {scen.affected_modules or ''}".lower()
            keyword_hits = sum(1 for term in all_query_terms if term in scen_text)
            keyword_score = min(1.0, keyword_hits * 0.3)

            age_days = (now - scen.updated_at.replace(tzinfo=timezone.utc)).total_seconds() / 86400.0
            recency = max(0.0, 1.0 - (age_days / 30.0))

            # Rank primarily by semantic relevance (50%), keyword match (35%), recency (10%)
            hybrid_score = (0.50 * sim) + (0.35 * keyword_score) + (0.10 * recency)
            if scen.status in ("open", "in_progress") and (sim >= 0.25 or keyword_hits > 0):
                hybrid_score += 0.05

            if hybrid_score >= 0.20 or keyword_hits > 0:
                scored_scens.append({
                    "score": hybrid_score,
                    "sim": sim,
                    "item": scen,
                    "type": "scenario_memory"
                })

        # Sort and select top candidates
        scored_mems.sort(key=lambda x: x["score"], reverse=True)
        scored_scens.sort(key=lambda x: x["score"], reverse=True)

        selected_items = []
        used_memory_ids = []
        top_scenario = scored_scens[0]["item"] if scored_scens else None

        # Add top scenario if relevant
        if scored_scens:
            selected_items.append(scored_scens[0])
            used_memory_ids.append(scored_scens[0]["item"].id)

        # Add top conversation memories
        for item in scored_mems:
            if len(selected_items) >= top_k:
                break
            selected_items.append(item)
            used_memory_ids.append(item["item"].id)

        if not selected_items:
            return {
                "used_memories": [],
                "used_memory_ids": [],
                "formatted_context": "",
                "previous_context_used": False,
                "top_scenario": None
            }

        # Update last_accessed_at on used records
        try:
            for s in selected_items:
                s["item"].last_accessed_at = now
            db.commit()
        except Exception as e:
            logger.warning(f"Could not update last_accessed_at: {e}")

        # Format with security delimiters and token/character budget limit
        formatted_lines = []
        char_count = 0
        query_words = query.strip().split()
        is_long_query = len(query_words) > 15

        for s in selected_items:
            entry = s["item"]
            if s["type"] == "scenario_memory":
                # For long standalone questions, do not inject prior scenario unless semantically relevant
                if is_long_query and s.get("sim", 0.0) < 0.35 and s.get("score", 0.0) < 0.45:
                    continue
                # Parse JSON fields safely
                modules = entry.affected_modules or "[]"
                findings = entry.confirmed_findings or "[]"
                solutions = entry.attempted_solutions or "[]"
                unresolved = entry.unresolved_questions or "[]"
                line = (
                    f"- [PRIOR SAP SCENARIO - Status: {entry.status.upper()}]\n"
                    f"  Title: {entry.scenario_title}\n"
                    f"  Symptoms: {entry.symptoms or 'Not specified'}\n"
                    f"  Affected Modules: {modules}\n"
                    f"  Confirmed Findings: {findings}\n"
                    f"  Attempted Solutions: {solutions}\n"
                    f"  Unresolved Questions: {unresolved}"
                )
            else:
                prov_label = entry.provenance
                if prov_label == "assistant_hypothesis":
                    prov_desc = "assistant_hypothesis (UNVERIFIED HYPOTHESIS - proposed by AI in previous turn, not verified SAP fact)"
                elif prov_label == "user_confirmed":
                    prov_desc = "user_confirmed (user verified this result in system)"
                elif prov_label == "kb_verified":
                    prov_desc = "kb_verified (verified against SAP documentation)"
                else:
                    prov_desc = "user_stated (user stated this fact or environment constraint)"

                line = f"- [MEMORY: {entry.memory_type.upper()} | Provenance: {prov_desc}]\n  Content: {entry.summary}"

            if char_count + len(line) > max_chars:
                break
            formatted_lines.append(line)
            char_count += len(line)

        formatted_context = "\n\n".join(formatted_lines)
        return {
            "used_memories": [
                {
                    "id": s["item"].id,
                    "type": s["type"],
                    "score": round(s["score"], 4)
                }
                for s in selected_items
            ],
            "used_memory_ids": used_memory_ids,
            "formatted_context": formatted_context,
            "previous_context_used": len(selected_items) > 0,
            "top_scenario": top_scenario
        }

    # =========================================================================
    # 4. CONDENSE QUERY ACROSS CHATS (Resolves pronouns & "that issue")
    # =========================================================================

    def condense_query_with_memory(
        self,
        query: str,
        retrieved_result: Dict[str, Any]
    ) -> str:
        """
        If incoming query is a cross-chat follow-up ('how do I check whether FI-CA posted both?',
        'what is the next step for that issue?', 'what about the previous scenario?'),
        enriches the query with context from earlier scenario memory so RAG retrieves correctly.
        """
        q = query.strip()
        q_lower = q.lower()

        top_scen = retrieved_result.get("top_scenario")
        if not top_scen:
            return q

        # Use strict word-boundary matching to prevent false substring matches (e.g. 'it' inside 'item' or 'activity')
        followup_patterns = [
            r"\b(it|this issue|that issue|the issue|that problem|the problem)\b",
            r"\b(the previous scenario|earlier scenario|previous scenario)\b",
            r"\b(what happens next|what is the next step|next step)\b",
            r"\b(is it resolved|did it post|both invoices|posted both)\b",
            r"\b(how do i check whether|how to check that)\b",
        ]

        has_followup_signal = any(re.search(pattern, q_lower) for pattern in followup_patterns)

        # Standalone, detailed scenario descriptions (e.g. > 15 words) must NOT be rewritten
        # with an earlier scenario unless the user explicitly refers to 'that issue' or 'previous scenario'
        words = q.split()
        explicit_reference = bool(re.search(r"\b(that issue|this issue|previous scenario|earlier scenario)\b", q_lower))
        is_conversational_followup = has_followup_signal and (len(words) <= 15 or explicit_reference)

        if is_conversational_followup:
            title = top_scen.scenario_title
            # Avoid repeating if title words are already fully present
            if not all(w.lower() in q_lower for w in title.split()[:3]):
                logger.info(f"Condensing cross-chat query '{q}' with scenario title: '{title}'")
                return f"{q} (regarding earlier scenario: {title})"

        return q

    # =========================================================================
    # 5. POST-RESPONSE BACKGROUND EXTRACTION & DEDUPLICATION
    # =========================================================================

    def extract_and_persist(
        self,
        db: Session,
        user_id: str,
        chat_id: str,
        user_message: str,
        assistant_message: str
    ) -> None:
        """
        Executes asynchronously after response delivery.
        Extracts preferences, technical environment details, structured scenario updates,
        and assistant hypotheses. Never blocks the user's turn.
        """
        if not self.get_user_memory_enabled(db, user_id):
            return

        clean_user_msg = self.redact_sensitive_data(user_message.strip())
        clean_asst_msg = self.redact_sensitive_data(assistant_message.strip())
        if not clean_user_msg:
            return

        now = datetime.now(timezone.utc)
        user_lower = clean_user_msg.lower()

        # A. Detect User Correction of Prior Memory
        # e.g., "Actually the document type is ZB not ZA", "Correction: it is in CC, not CI"
        correction_match = re.search(
            r"(?i)\b(actually|correction|it is not|not in|rather than|instead of|mistake|clarification)\b",
            clean_user_msg
        )
        if correction_match:
            # Find and supersede active memories containing conflicting terms
            active_mems = db.query(ConversationMemory).filter(
                ConversationMemory.user_id == user_id,
                ConversationMemory.status == "active"
            ).all()
            for old_mem in active_mems:
                words = [w for w in re.findall(r"\b[A-Za-z0-9_\-]{3,}\b", old_mem.summary.lower())]
                overlap = sum(1 for w in words if w in user_lower)
                if overlap >= 2:
                    old_mem.status = "superseded"
                    old_mem.updated_at = now
                    logger.info(f"Superseded memory id={old_mem.id} due to user correction")

        # B. Extract User Preferences / Environment Assumptions
        env_match = re.search(
            r"(?i)\b(we are using|we use|our system is|our environment is|we run|running on|s/4hana \d{4}|clean core|on-premise|private cloud|public cloud)\b",
            clean_user_msg
        )
        if env_match:
            self._persist_conversation_memory(
                db=db,
                user_id=user_id,
                chat_id=chat_id,
                memory_type="environment",
                summary=clean_user_msg,
                provenance="user_stated",
                confidence=1.0
            )

        # Standing format preference (e.g. "always give short answers", "from now on no diagrams")
        standing_format_match = re.search(
            r"(?i)\b(always|from now on)\b.*?(\b(short answer|concise|brief|only points|points|bullet points|no diagram|without diagram|in detail|detailed|table|steps)\b)",
            clean_user_msg
        ) or re.search(
            r"(?i)\b(always|from now on)\b\s+(give|provide|use|write|reply|respond|answer|prefer)\b",
            clean_user_msg
        )
        pref_match = re.search(
            r"(?i)\b(i prefer|please explain step-by-step|keep it concise|give technical details|show t-codes|provide spro paths)\b",
            clean_user_msg
        )

        if standing_format_match:
            # Supersede prior active format preferences for this user
            prev_prefs = db.query(ConversationMemory).filter(
                ConversationMemory.user_id == user_id,
                ConversationMemory.memory_type == "preference",
                ConversationMemory.status == "active"
            ).all()
            for p in prev_prefs:
                if any(k in p.summary.lower() for k in ["diagram", "short", "detail", "point", "table", "step", "concise"]):
                    p.status = "superseded"
                    p.updated_at = now
                    logger.info(f"Superseded prior format preference id={p.id}")

            self._persist_conversation_memory(
                db=db,
                user_id=user_id,
                chat_id=chat_id,
                memory_type="preference",
                summary=clean_user_msg,
                provenance="user_stated",
                confidence=1.0
            )
        elif pref_match:
            self._persist_conversation_memory(
                db=db,
                user_id=user_id,
                chat_id=chat_id,
                memory_type="preference",
                summary=clean_user_msg,
                provenance="user_stated",
                confidence=1.0
            )

        # C. Extract Production Incident / Business Scenario
        incident_signals = [
            "error", "failed", "duplicate", "dump", "short dump", "exception",
            "invoice", "billing document", "subscription order", "billable item",
            "fpc1", "fpc2", "fpe1", "fpy1", "crmd_order", "odi", "reconciliation"
        ]
        has_incident_signal = any(sig in user_lower for sig in incident_signals)

        if has_incident_signal:
            entities = self.extract_sap_entities(clean_user_msg)
            modules = entities["modules"]
            tcodes = entities["tcodes"]
            tables = entities["tables"]

            # Scenario Title
            scenario_title = " ".join(clean_user_msg.split()[:8])
            if len(clean_user_msg.split()) > 8:
                scenario_title += "..."

            # Check if there is an existing scenario for this user to update or create new
            existing_scenario = (
                db.query(SAPScenarioMemory)
                .filter(
                    SAPScenarioMemory.user_id == user_id,
                    SAPScenarioMemory.status.in_(["open", "in_progress"])
                )
                .order_by(SAPScenarioMemory.updated_at.desc())
                .first()
            )

            # Determine whether this relates to existing open scenario
            relates_to_existing = False
            if existing_scenario:
                # check overlap with existing scenario title or symptoms
                ex_words = set(re.findall(r"\b[A-Za-z0-9_\-]{3,}\b", existing_scenario.scenario_title.lower()))
                cur_words = set(re.findall(r"\b[A-Za-z0-9_\-]{3,}\b", clean_user_msg.lower()))
                if len(ex_words & cur_words) >= 2 or any(m in (existing_scenario.affected_modules or "") for m in modules):
                    relates_to_existing = True

            # Extract assistant hypotheses vs suggested steps
            hypotheses = []
            steps = []
            if clean_asst_msg:
                # Check for hypothesis markers in assistant message
                for line in clean_asst_msg.split("\n"):
                    line_str = line.strip()
                    if any(term in line_str.lower() for term in ["hypothesis", "likely cause", "potential reason", "possible root cause"]):
                        hypotheses.append(line_str)
                    elif any(term in line_str.lower() for term in ["step 1", "step 2", "check transaction", "execute", "verify in"]):
                        steps.append(line_str[:200])

            if relates_to_existing and existing_scenario:
                # Update existing scenario
                curr_steps = json.loads(existing_scenario.investigation_steps or "[]")
                curr_hypo = json.loads(existing_scenario.hypotheses or "[]")
                curr_steps.extend(steps[:3])
                curr_hypo.extend(hypotheses[:3])

                existing_scenario.investigation_steps = json.dumps(list(set(curr_steps))[:10])
                existing_scenario.hypotheses = json.dumps(list(set(curr_hypo))[:10])
                existing_scenario.updated_at = now
                db.commit()
                logger.info(f"Updated existing SAP scenario id={existing_scenario.id}")
            else:
                # Create new structured scenario memory
                try:
                    scen_emb = embedding_service.embed_text(f"{scenario_title} {clean_user_msg}")
                except Exception:
                    scen_emb = None

                new_scenario = SAPScenarioMemory(
                    user_id=user_id,
                    scenario_title=scenario_title,
                    symptoms=clean_user_msg,
                    affected_modules=json.dumps(modules),
                    entities=json.dumps({"tcodes": tcodes, "tables": tables}),
                    investigation_steps=json.dumps(steps[:5]),
                    confirmed_findings=json.dumps([]),
                    attempted_solutions=json.dumps([]),
                    unresolved_questions=json.dumps([clean_user_msg]),
                    hypotheses=json.dumps(hypotheses[:5]),
                    status="open",
                    embedding=scen_emb,
                    source_chat_id=chat_id,
                    created_at=now,
                    updated_at=now
                )
                db.add(new_scenario)
                db.commit()
                logger.info(f"Created new SAP scenario memory for user_id={user_id}")

            # Also store user-stated fact in ConversationMemory
            self._persist_conversation_memory(
                db=db,
                user_id=user_id,
                chat_id=chat_id,
                memory_type="issue",
                summary=clean_user_msg,
                provenance="user_stated",
                confidence=1.0,
                entities={"modules": modules, "tcodes": tcodes, "tables": tables}
            )

        # D. Assistant Hypotheses: if assistant made specific diagnostic hypotheses,
        # persist them explicitly labeled as assistant_hypothesis (unverified)
        if clean_asst_msg:
            hypothesis_lines = [
                line.strip() for line in clean_asst_msg.split("\n")
                if any(m in line.lower() for m in ["likely hypothesis", "hypothesized", "potential root cause:"])
            ]
            for h in hypothesis_lines[:2]:
                if len(h) > 15:
                    self._persist_conversation_memory(
                        db=db,
                        user_id=user_id,
                        chat_id=chat_id,
                        memory_type="assumption",
                        summary=h,
                        provenance="assistant_hypothesis",
                        confidence=0.7
                    )

        # E. Update rolling chat summary in ConversationSummary
        self._update_chat_summary(db, user_id, chat_id, clean_user_msg)

    def _persist_conversation_memory(
        self,
        db: Session,
        user_id: str,
        chat_id: str,
        memory_type: str,
        summary: str,
        provenance: str,
        confidence: float = 1.0,
        entities: Optional[Any] = None
    ) -> Optional[ConversationMemory]:
        """Persists a single ConversationMemory fact with deduplication."""
        clean_text = self.redact_sensitive_data(summary.strip())
        if not clean_text or len(clean_text) < 5:
            return None

        c_hash = self.compute_content_hash(clean_text)
        now = datetime.now(timezone.utc)

        # Exact deduplication via hash
        existing = db.query(ConversationMemory).filter(
            ConversationMemory.user_id == user_id,
            ConversationMemory.content_hash == c_hash,
            ConversationMemory.status == "active"
        ).first()

        if existing:
            existing.updated_at = now
            existing.last_accessed_at = now
            db.commit()
            return existing

        # Compute embedding
        try:
            emb = embedding_service.embed_text(clean_text)
        except Exception as e:
            logger.warning(f"Failed to embed memory text: {e}")
            emb = None

        new_mem = ConversationMemory(
            user_id=user_id,
            memory_type=memory_type,
            summary=clean_text,
            entities=json.dumps(entities) if entities is not None else None,
            provenance=provenance,
            status="active",
            confidence=confidence,
            embedding=emb,
            content_hash=c_hash,
            source_chat_id=chat_id,
            created_at=now,
            updated_at=now,
            last_accessed_at=now
        )
        db.add(new_mem)
        db.commit()
        db.refresh(new_mem)
        return new_mem

    def _update_chat_summary(
        self,
        db: Session,
        user_id: str,
        chat_id: str,
        latest_message: str
    ) -> None:
        """Updates rolling conversation summary for the given chat."""
        now = datetime.now(timezone.utc)
        summary_record = db.query(ConversationSummary).filter(
            ConversationSummary.user_id == user_id,
            ConversationSummary.chat_id == chat_id
        ).first()

        extracted = self.extract_sap_entities(latest_message)
        modules = extracted["modules"]
        tcodes = extracted["tcodes"]

        if summary_record:
            # Append topic to summary
            existing_entities = json.loads(summary_record.key_entities or "[]")
            combined_entities = list(set(existing_entities + modules + tcodes))
            summary_record.key_entities = json.dumps(combined_entities)
            summary_record.updated_at = now
            db.commit()
        else:
            new_summary = ConversationSummary(
                user_id=user_id,
                chat_id=chat_id,
                summary=f"Chat discussing {', '.join(modules) if modules else 'SAP BRIM scenario'}: {latest_message[:150]}",
                key_entities=json.dumps(modules + tcodes),
                unresolved_topics=json.dumps([latest_message[:100]]),
                updated_at=now
            )
            db.add(new_summary)
            db.commit()


memory_service = MemoryService()
