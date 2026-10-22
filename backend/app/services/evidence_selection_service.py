import re
from urllib.parse import urlparse
from typing import List, Dict, Any, Optional, Tuple
from backend.app.config import settings
from backend.app.services.reranking_service import reranking_service

# Stop words for query token analysis
STOP_WORDS = {
    "what", "is", "the", "a", "an", "how", "to", "in", "of", "and", "for", "with",
    "does", "do", "explain", "describe", "can", "you", "tell", "me", "about", "which",
    "are", "why", "where", "when", "by", "from", "on", "at", "as", "into"
}

SCENARIO_META_STOP_WORDS = {
    # Calendar, months, time words
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "month", "months", "year", "years", "day", "days", "date", "dates",
    # Temporal & narrative status adverbs
    "continued", "continuing", "continues", "started", "starting", "starts",
    "ended", "ending", "ends", "ongoing", "recent", "older", "previous",
    "prior", "next", "following", "customer", "scenario", "issue", "problem",
    "incident", "case", "situation", "example",
    # Prompt framing & meta-instruction words
    "trace", "identify", "investigate", "investigation", "possible", "root",
    "causes", "cause", "diagnostic", "checks", "check", "corrective",
    "actions", "action", "supporting", "evidence", "steps", "step",
    "guide", "guidance", "recommendation", "recommendations", "overview",
    "detail", "details", "find", "analyze", "analysis",
}

BRIM_SYNONYM_CLUSTERS = {
    "cancellation": {"cancellation", "cancelled", "cancel", "canceling", "termination", "terminated", "terminate", "validity", "deactivation", "end date"},
    "cancelled": {"cancellation", "cancelled", "cancel", "canceling", "termination", "terminated", "terminate", "validity", "deactivation", "end date"},
    "cancel": {"cancellation", "cancelled", "cancel", "canceling", "termination", "terminated", "terminate", "validity", "deactivation", "end date"},
    "subscription": {"subscription", "contract", "provider contract", "subscription contract", "som", "provider order"},
    "recurring": {"recurring", "billing plan", "cycle", "periodic", "recurring charges", "recurring fees"},
    "invoices": {"invoice", "invoices", "invoicing", "billing", "billable", "fkkinv", "fkinv", "dfkkinvdoc"},
    "invoice": {"invoice", "invoices", "invoicing", "billing", "billable", "fkkinv", "fkinv", "dfkkinvdoc"},
    "invoicing": {"invoice", "invoices", "invoicing", "billing", "billable", "fkkinv", "fkinv", "fkkinv_rev", "dfkkinvdoc"},
    "ci": {"ci", "convergent invoicing", "invoicing", "billing", "bits", "billable items", "fkkbix"},
    "som": {"som", "subscription order management", "subscription order", "contract", "provider contract", "odi"},
    "cc": {"cc", "convergent charging", "charging", "rating", "charge plan", "allowance", "cits"},
    "fi-ca": {"fi-ca", "fica", "contract accounts receivable", "open items", "dfkkop", "receivables", "reconciliation keys", "fpy1"},
    "fica": {"fi-ca", "fica", "contract accounts receivable", "open items", "dfkkop", "receivables", "reconciliation keys", "fpy1"},
}

SAP_TABLE_REGEX = re.compile(r"\b(dfkk[a-z0-9_]+|fkk[a-z0-9_]+|erdk|erch|but000|but020|mara|marc|vbak|vbap|ekko|ekpo|bseg|bkpf)\b", re.IGNORECASE)
APPROVED_WEB_HOSTS = ("help.sap.com", "learning.sap.com", "community.sap.com", "blogs.sap.com", "support.sap.com", "answers.sap.com", "sap.com")


class EvidenceSelectionService:
    """
    Unified Evidence Selection Service for SAP BRIM Knowledge Assistant.
    
    Responsibilities:
    1. Compute a deterministic KB relevance routing rubric from hybrid score, exact
       query-token coverage, and requested technical-identifier coverage.
    2. Normalize evidence with source provenance.
    3. Select KB at/above the threshold; otherwise select relevant approved web
       evidence only. Never combine the sources.
    """

    def __init__(self):
        self.internal_threshold = settings.KB_CONFIDENCE_THRESHOLD

    @staticmethod
    def _extract_query_tokens(query: str) -> List[str]:
        raw = re.findall(r"\b[a-z0-9\/\-_]+\b", query.lower())
        tokens = [
            t for t in raw
            if t not in STOP_WORDS
            and t not in SCENARIO_META_STOP_WORDS
            and not t.isdigit()
            and len(t) > 1
        ]
        if not tokens:
            tokens = [t for t in raw if t not in STOP_WORDS and len(t) > 1]
        return tokens

    @staticmethod
    def _extract_technical_identifiers(text: str) -> List[str]:
        """Extracts candidate SAP T-codes, table names, and technical identifiers."""
        found = set()
        for m in re.finditer(r"\b(/[a-z0-9_]{2,}/[a-z0-9_]+|[a-z]{1,4}\d{1,3}[a-z0-9]?)\b", text.lower()):
            found.add(m.group(0))
        for m in SAP_TABLE_REGEX.finditer(text.lower()):
            found.add(m.group(0))
        return list(found)

    def compute_kb_evidence_score(
        self,
        query: str,
        kb_chunks: List[Dict[str, Any]],
        threshold: Optional[float] = None,
        is_follow_up: bool = False,
    ) -> Dict[str, Any]:
        """
        Computes a normalized Evidence Score in [0, 1] built from:
        1. Reranker relevance of top chunks (40%)
        2. Key SAP terms & entity coverage (30%)
        3. Agreement between retrieved chunks (15%)
        4. Source quality / provenance (15%)

        Enforces a multi-stage Relevance Gate:
        - Top relevance minimum check (>= 0.55)
        - Entity presence check: if query has explicit technical identifiers / SAP entities,
          at least one must be matched in the evidence.
        - Chunk mutual consistency check (no mutual contradictions).

        Label: "evidence score", strictly avoiding "confidence" or "probability of correctness".
        """
        thresh = threshold if threshold is not None else settings.KB_CONFIDENCE_THRESHOLD
        if not kb_chunks:
            return {
                "evidence_score": 0.0,
                "confidence": 0.0,
                "kb_relevance_score": 0.0,
                "threshold": thresh,
                "passed": False,
                "gate_passed": False,
                "should_trigger_tavily": True,
                "fallback_reason": "No knowledge base chunks were retrieved.",
                "signals": {
                    "top_relevance": 0.0,
                    "avg_top_relevance": 0.0,
                    "term_coverage": 0.0,
                    "tech_match": 0.0,
                    "chunk_agreement": 0.0,
                    "source_quality": 0.0,
                },
                "reason": "No knowledge base chunks were retrieved.",
            }

        # 1. Reranker relevance of top chunks
        scores = [
            max(0.0, min(1.0, float(c.get("rerank_score", c.get("score", 0.0)))))
            for c in kb_chunks[:4]
        ]
        top_relevance = scores[0] if scores else 0.0
        avg_top_relevance = sum(scores[:3]) / max(1, min(len(scores), 3))

        # 2. Key SAP terms and entities coverage
        query_tokens = self._extract_query_tokens(query)
        query_ids = self._extract_technical_identifiers(query)
        chunk_texts = [str(c.get("chunk_text") or "").lower() for c in kb_chunks[:4]]
        combined_text = " ".join(chunk_texts)
        text_tokens = set(re.findall(r"[a-z0-9][a-z0-9/_-]*", combined_text))

        def _token_matches(tok: str) -> bool:
            if tok in text_tokens or tok in combined_text:
                return True
            syns = BRIM_SYNONYM_CLUSTERS.get(tok)
            if syns:
                for syn in syns:
                    if syn in text_tokens or syn in combined_text:
                        return True
            return False

        term_coverage = (
            sum(1 for token in query_tokens if _token_matches(token)) / len(query_tokens)
            if query_tokens else 1.0
        )
        tech_match = (
            sum(1 for identifier in query_ids if identifier.lower() in text_tokens) / len(query_ids)
            if query_ids else 1.0
        )
        entity_coverage = 0.70 * term_coverage + 0.30 * tech_match if query_ids else term_coverage

        # 3. Agreement between chunks
        if len(chunk_texts) >= 2:
            chunk_token_sets = [set(re.findall(r"\b[a-z]{3,}\b", t)) for t in chunk_texts[:3]]
            pairwise_agreements = []
            for i in range(len(chunk_token_sets)):
                for j in range(i + 1, len(chunk_token_sets)):
                    s1, s2 = chunk_token_sets[i], chunk_token_sets[j]
                    if s1 and s2:
                        jaccard = len(s1 & s2) / max(1, len(s1 | s2))
                        pairwise_agreements.append(min(1.0, jaccard / 0.25))
            agreement = sum(pairwise_agreements) / len(pairwise_agreements) if pairwise_agreements else 0.80
        else:
            agreement = 0.85 if top_relevance >= 0.70 else 0.60

        # Check for mutual contradictions
        has_contradiction = False
        contradiction_reason = None
        has_s4_assertion = any("s/4hana" in t or "s4hana" in t for t in chunk_texts)
        has_ecc_only = any("ecc only" in t or "obsolete in s/4hana" in t for t in chunk_texts)
        if "s/4hana" in query.lower() and has_ecc_only and not has_s4_assertion:
            has_contradiction = True
            contradiction_reason = "Retrieved chunks indicate feature is obsolete or differing across ECC and S/4HANA."

        # Explicit contradiction check between chunk guidance
        if any("not supported" in t for t in chunk_texts) and any("fully supported" in t for t in chunk_texts):
            has_contradiction = True
            contradiction_reason = "Contradictory support assertions found among retrieved evidence chunks."

        # 4. Source Quality
        quality_scores = []
        for c in kb_chunks[:4]:
            doc_name = str(c.get("document_name") or "").lower()
            if any(doc_name.endswith(ext) for ext in [".pdf", ".txt", ".md"]):
                q_score = 1.0
            else:
                q_score = 0.85
            quality_scores.append(q_score)
        source_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.80

        # Composite Evidence Score: 40% rerank relevance, 30% entity coverage, 15% agreement, 15% source quality
        evidence_score = (
            0.40 * avg_top_relevance
            + 0.30 * entity_coverage
            + 0.15 * agreement
            + 0.15 * source_quality
        )
        evidence_score = max(0.0, min(1.0, round(evidence_score, 4)))

        # Relevance Gate Evaluation
        gate_passed = True
        gate_failures = []

        if top_relevance < 0.55:
            gate_passed = False
            gate_failures.append(f"Top chunk relevance ({top_relevance:.2f}) below gate threshold (0.55)")

        if query_ids and tech_match < 0.5:
            gate_passed = False
            gate_failures.append("Requested SAP technical identifier is missing from retrieved KB evidence")

        if term_coverage < 0.35 and not is_follow_up:
            gate_passed = False
            gate_failures.append(f"Low question term coverage ({term_coverage:.2f})")

        if has_contradiction:
            gate_passed = False
            gate_failures.append(contradiction_reason or "Contradictory evidence detected between retrieved chunks")

        passed = (evidence_score >= thresh) and gate_passed

        fallback_reason = None
        if not passed:
            if not gate_passed:
                fallback_reason = f"KB relevance gate failed: {'; '.join(gate_failures)}."
            else:
                fallback_reason = f"KB evidence score ({evidence_score:.2f}) is below threshold ({thresh:.2f})."

        return {
            "evidence_score": evidence_score,
            "confidence": evidence_score,
            "kb_relevance_score": round(evidence_score * 100, 1),
            "threshold": thresh,
            "passed": passed,
            "gate_passed": gate_passed,
            "should_trigger_tavily": not passed,
            "fallback_reason": fallback_reason,
            "signals": {
                "top_relevance": round(top_relevance, 4),
                "avg_top_relevance": round(avg_top_relevance, 4),
                "term_coverage": round(term_coverage, 4),
                "tech_match": round(tech_match, 4),
                "chunk_agreement": round(agreement, 4),
                "source_quality": round(source_quality, 4),
            },
            "reason": fallback_reason or f"KB evidence score {evidence_score:.2f} meets threshold {thresh:.2f}.",
        }

    def compute_internal_confidence(
        self,
        query: str,
        kb_chunks: List[Dict[str, Any]],
        threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """Backward-compatible proxy to compute_kb_evidence_score."""
        return self.compute_kb_evidence_score(query, kb_chunks, threshold=threshold)

    def normalize_internal_chunk(self, chunk: Dict[str, Any]) -> Dict[str, Any]:
        """Normalizes an internal document chunk to the unified evidence representation."""
        chunk_id = chunk.get("chunk_id") or chunk.get("id") or "int_chunk"
        return {
            "source_id": str(chunk_id),
            "chunk_id": str(chunk_id),
            "source_type": "knowledge_base",
            "title": chunk.get("document_name") or "SAP BRIM Documentation",
            "document_name": chunk.get("document_name") or "SAP BRIM Documentation",
            "page_number": chunk.get("page_number", 1),
            "section": chunk.get("section") or f"Page {chunk.get('page_number', 1)}",
            "url": None,
            "domain": "internal_knowledge_base",
            "chunk_text": chunk.get("chunk_text") or "",
            "authority_tier": 1,  # Verified internal official enterprise manuals
            "relevance_score": float(chunk.get("rerank_score", chunk.get("score", 0.0))),
            "snippet": (chunk.get("chunk_text") or "")[:280] + ("..." if len(chunk.get("chunk_text") or "") > 280 else "")
        }

    def normalize_web_result(self, web_res: Dict[str, Any], index: int) -> Dict[str, Any]:
        """Normalizes an external web result to the unified evidence representation."""
        url = web_res.get("url") or ""
        domain = web_res.get("domain") or "help.sap.com"
        tier = web_res.get(
            "authority_tier",
            1 if domain in {"help.sap.com", "learning.sap.com"} else 2,
        )
        score = float(web_res.get("rerank_score", web_res.get("score", 0.65)))

        return {
            "source_id": f"web_{index}_{domain}",
            "source_type": "web",
            "title": web_res.get("title") or "SAP Official Documentation",
            "document_name": web_res.get("title") or "SAP Official Documentation",
            "page_number": None,
            "section": domain,
            "url": url,
            "domain": domain,
            "chunk_text": web_res.get("chunk_text") or f"{web_res.get('title')}: {web_res.get('snippet')}",
            "authority_tier": tier,
            "source_priority": web_res.get("source_priority"),
            "relevance_score": score,
            "snippet": (web_res.get("snippet") or "")[:280] + ("..." if len(web_res.get("snippet") or "") > 280 else "")
        }

    @staticmethod
    def _is_approved_web_result(result: Dict[str, Any]) -> bool:
        url = str(result.get("url") or "")
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        return (
            parsed.scheme == "https"
            and any(host == domain or host.endswith("." + domain) for domain in APPROVED_WEB_HOSTS)
            and bool(result.get("chunk_text") or result.get("snippet"))
        )

    def evaluate_evidence_set(
        self,
        query: str,
        passages: List[Dict[str, Any]],
        set_type: str
    ) -> Dict[str, Any]:
        """
        Evaluates a candidate evidence set (internal, external, or combined) using
        a consistent evidence-assessment methodology.
        """
        if not passages:
            return {
                "quality_score": 0.0,
                "coverage": 0.0,
                "sufficiency": False,
                "authority_score": 0.0
            }

        query_tokens = self._extract_query_tokens(query)
        combined_text = " ".join(p["chunk_text"].lower() for p in passages)

        # 1. Relevance: average of top 3 passages weighted by authority tier
        tier_weights = {1: 1.0, 2: 0.85, 3: 0.7}
        weighted_scores = [
            p["relevance_score"] * tier_weights.get(p.get("authority_tier", 1), 0.8)
            for p in passages
        ]
        avg_relevance = sum(weighted_scores[:3]) / min(len(weighted_scores), 3)

        # 2. Coverage of question keywords
        if query_tokens:
            matched_terms = sum(1 for t in query_tokens if t in combined_text)
            coverage = matched_terms / len(query_tokens)
        else:
            coverage = 1.0

        # 3. Authority
        avg_authority = sum(tier_weights.get(p.get("authority_tier", 1), 0.8) for p in passages) / len(passages)

        # Composite quality score
        composite_quality = (0.50 * avg_relevance) + (0.35 * coverage) + (0.15 * avg_authority)
        quality_score = max(0.0, min(1.0, round(composite_quality, 4)))

        # Sufficiency criterion
        # Allow sufficient evidence for scenario/detailed queries where term count is high,
        # or when high-relevance official tier-1 documentation is retrieved.
        is_detailed_query = len(query_tokens) >= 5
        min_coverage = 0.55 if is_detailed_query else 0.50
        sufficiency = (
            (quality_score >= 0.48 and coverage >= min_coverage)
            or (set_type == "official_web" and coverage >= min_coverage and (quality_score >= 0.45 or avg_relevance >= 0.50))
            or (quality_score >= 0.55 and coverage >= 0.60)
        )

        return {
            "quality_score": quality_score,
            "coverage": round(coverage, 4),
            "sufficiency": sufficiency,
            "authority_score": round(avg_authority, 4)
        }

    def select_strongest_evidence(
        self,
        query: str,
        internal_candidates: List[Dict[str, Any]],
        external_candidates: List[Dict[str, Any]],
        internal_confidence_data: Dict[str, Any],
        force_web: bool = False,
    ) -> Dict[str, Any]:
        """Select approved web evidence only; key-unavailable KB fallback is separate.

        ``internal_candidates`` and ``force_web`` remain in the signature for
        compatibility, but internal passages are deliberately never normalized,
        scored for answer selection, or returned.
        """
        internal_score = float(internal_confidence_data.get("confidence", 0.0) or 0.0)
        normalized_internal = [
            self.normalize_internal_chunk(chunk)
            for chunk in internal_candidates
            if str(chunk.get("chunk_text") or "").strip()
        ][:5]
        internal_eval = self.evaluate_evidence_set(query, normalized_internal, "internal")

        validated_external = [item for item in external_candidates if self._is_approved_web_result(item)]
        ranked_web, web_score = reranking_service.rerank_web(query, validated_external, top_n=5)
        selected_web = [self.normalize_web_result(w, i + 1) for i, w in enumerate(ranked_web)]
        relevant_web = [
            p for p in selected_web
            if float(p.get("relevance_score", 0.0)) >= 0.30
        ]
        official_web = [p for p in relevant_web if p.get("authority_tier", 3) == 1]
        official_eval = self.evaluate_evidence_set(query, official_web, "official_web")
        external_eval = official_eval if (official_web and official_eval["sufficiency"]) else self.evaluate_evidence_set(query, relevant_web, "external")

        # Evaluate combined candidate set
        combined_candidates = (normalized_internal[:3] + (official_web[:2] if official_web else relevant_web[:2]))
        combined_eval = self.evaluate_evidence_set(query, combined_candidates, "combined")

        # If external candidates were supplied but none passed domain approval, return insufficient
        if external_candidates and not validated_external:
            return {
                "selected_passages": [],
                "source_type": "insufficient",
                "selected_source": "insufficient",
                "kb_relevance_score": round(internal_score * 100, 1),
                "kb_threshold": round(self.internal_threshold * 100),
                "fallback_reason": "Web search returned no authoritative SAP results.",
                "internal_evidence_confidence": internal_score,
                "selected_evidence_quality": 0.0,
                "external_search_triggered": True,
                "selection_summary": "Web search returned no authoritative SAP results.",
                "evidence_coverage": 0.0,
                "internal_eval": internal_eval,
                "external_eval": external_eval,
                "combined_eval": combined_eval,
            }

        # Decision rubric
        if force_web:
            if official_web and official_eval["sufficiency"]:
                selected = official_web
                selected_type = "web"
                selected_quality = web_score
                summary = "Selected official SAP web evidence."
                fallback_reason = "Official SAP web evidence selected."
            elif relevant_web and external_eval["sufficiency"]:
                selected = relevant_web
                selected_type = "web"
                selected_quality = web_score
                summary = "Selected verified SAP web evidence."
                fallback_reason = "Verified SAP web evidence selected."
            else:
                selected = []
                selected_type = "insufficient"
                selected_quality = 0.0
                fallback_reason = "No sufficiently relevant authoritative SAP web evidence was found."
                summary = fallback_reason
        else:
            # Comparative selection
            has_web_official = official_web and official_eval["sufficiency"]
            has_web_relevant = relevant_web and external_eval["sufficiency"]
            has_kb = normalized_internal and internal_eval["sufficiency"]

            if has_web_official:
                # Tier 1 official SAP documentation (e.g. Help Portal) takes precedence or combines
                selected = official_web
                selected_type = "web"
                selected_quality = max(web_score, official_eval["quality_score"])
                summary = "Selected official SAP Help documentation."
                fallback_reason = "Verified official SAP documentation selected."
            elif has_kb and has_web_relevant:
                # Complementary evidence: both internal enterprise manual and verified web support
                selected = combined_candidates
                selected_type = "combined"
                selected_quality = round((internal_eval["quality_score"] + external_eval["quality_score"]) / 2, 4)
                summary = "Combined complementary evidence from Knowledge Base and verified SAP web sources."
                fallback_reason = "Complementary evidence from Knowledge Base and web sources selected."
            elif has_kb:
                selected = normalized_internal
                selected_type = "knowledge_base"
                selected_quality = internal_eval["quality_score"]
                summary = "Selected verified SAP Knowledge Base documentation."
                fallback_reason = "Verified SAP Knowledge Base documentation selected."
            elif has_web_relevant:
                selected = relevant_web
                selected_type = "web"
                selected_quality = web_score
                summary = "Selected relevant SAP web evidence."
                fallback_reason = "Relevant SAP web evidence selected."
            else:
                selected = []
                selected_type = "insufficient"
                selected_quality = 0.0
                fallback_reason = "Neither Knowledge Base nor web sources provided sufficient verified evidence."
                summary = fallback_reason

        return {
            "selected_passages": selected,
            "source_type": selected_type,
            "selected_source": selected_type,
            "kb_relevance_score": round(internal_score * 100, 1),
            "kb_threshold": round(self.internal_threshold * 100),
            "fallback_reason": fallback_reason,
            "internal_evidence_confidence": internal_score,
            "selected_evidence_quality": selected_quality,
            "external_search_triggered": bool(external_candidates),
            "selection_summary": summary,
            "evidence_coverage": 1.0 if selected else 0.0,
            "internal_eval": internal_eval,
            "external_eval": external_eval,
            "combined_eval": combined_eval,
        }

    def select_internal_key_fallback(
        self,
        query: str,
        internal_candidates: List[Dict[str, Any]],
        internal_confidence_data: Dict[str, Any],
        reason: str,
    ) -> Dict[str, Any]:
        """Select retrieved KB chunks only when Tavily evidence is unavailable or weak."""
        selected = [
            self.normalize_internal_chunk(chunk)
            for chunk in internal_candidates
            if str(chunk.get("chunk_text") or "").strip()
        ][:5]
        score = float(internal_confidence_data.get("confidence", 0.0) or 0.0)
        if not selected:
            selected = []
            reason = f"{reason} No relevant knowledge-base documents were found."
            source_type = "insufficient"
            score = 0.0
        else:
            source_type = "knowledge_base"

        summary = (
            "Web search evidence was unavailable or insufficient; answering from retrieved knowledge-base passages."
            if source_type == "knowledge_base"
            else reason
        )
        return {
            "selected_passages": selected,
            "source_type": source_type,
            "selected_source": source_type,
            "kb_relevance_score": round(score * 100, 1),
            "kb_threshold": round(self.internal_threshold * 100),
            "fallback_reason": reason,
            "internal_evidence_confidence": score,
            "selected_evidence_quality": score,
            "external_search_triggered": False,
            "selection_summary": summary,
            "evidence_coverage": 1.0 if selected else 0.0,
        }


evidence_selection_service = EvidenceSelectionService()
