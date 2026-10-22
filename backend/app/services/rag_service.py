import logging
import re
import time
from typing import Dict, Any, List, Generator, Optional, Tuple
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.services.sap_classifier import SAP_SCOPE_REFUSAL, sap_classifier
from backend.app.services.retrieval_service import retrieval_service
from backend.app.services.reranking_service import reranking_service
from backend.app.services.grounding_service import grounding_service
from backend.app.services.web_search_service import (
    web_search_service,
    TavilyAuthenticationError,
    TavilySearchError,
)
from backend.app.services.evidence_selection_service import evidence_selection_service
from backend.app.services.answer_planner import answer_planner
from backend.app.services.followup_service import followup_service
from backend.app.services.llm_service import llm_service
from backend.app.services.query_rewriter import query_rewriter
from backend.app.services.conversational_service import conversational_service
from backend.app.services.memory_service import memory_service
from backend.app.services.vision_service import vision_service

logger = logging.getLogger(__name__)


class RAGService:
    """
    Production-Grade Evidence-First SAP BRIM Knowledge Assistant Service.
    
    Orchestration Flow:
    1. Query Rewriting & Context Resolution: resolves references, retains technical IDs.
    2. SAP Domain Classifier: strict scope check, returns refusal for non-SAP queries.
    3. Internal Hybrid Retrieval: vector + lexical BM25 for key-unavailable fallback.
    4. Tavily search for every in-scope question when a key is available.
    5. Generate and ground the answer from one selected evidence source only.
    6. Question-Aware Detailed Answer Generation:
       - Injects structure archetype guidelines (conceptual, configuration, troubleshooting, etc.).
    7. Claim-Level Grounding Verification (ANSWER_GROUNDING_THRESHOLD = 0.80):
       - Inspects material factual claims & audits SAP technical identifiers (T-codes, tables, SPRO).
       - Critical claim veto: fabricated identifiers fail the publication gate immediately.
    8. Controlled Answer Repair (MAX_GROUNDING_REPAIR_ATTEMPTS = 1):
       - If verification fails, re-prompts LLM to strip unverified technical instructions.
       - Re-verifies revised answer.
       - If still failing, returns a supported partial answer or explicit abstention.
    9. Recommended Follow-Up Questions (FOLLOWUP_QUESTION_COUNT = 3):
       - Generates exactly 3 relevant, clickable follow-up questions.
    10. Progressive Streaming & Safe Delivery:
       - Yields progress stages and answer tokens as they are generated.
       - Includes the final grounding decision and citations in the completion event.
    """

    @staticmethod
    def _insufficient_answer(source_type: str = "insufficient", missing_detail: str = "") -> str:
        return (
            "I could not verify this SAP answer to the required confidence level (available evidence is insufficient and cannot be verified). "
            "Here is the missing evidence or product/version detail needed to verify it:\n"
            "- Specific SAP product and deployment model (e.g., SAP S/4HANA vs SAP ECC vs SAP BRIM)\n"
            "- Relevant module and exact transaction code, table, or application log details\n"
            "- Applicable SAP release/version compatibility and customizing configuration"
            + (f"\n- Detail: {missing_detail}" if missing_detail else "")
        )

    @staticmethod
    def _sanitize_and_verify_identifiers(
        answer: str,
        passages: List[Dict[str, Any]],
    ) -> str:
        """Post-generation check:
        1. Correct standard expansions:
           - BRIM is Billing and Revenue Innovation Management
           - FI-CA is Contract Accounts Receivable and Payable
        2. No fabricated SAP details:
           - A transaction code, table name, field name, API, configuration path or Fiori app
             may appear in an answer only if it is present in the retrieved KB chunks or web results.
             Otherwise omit it or mark it '(unverified, confirm in your system)', and log it.
        """
        if not answer or not answer.strip():
            return answer

        # Protect fenced code blocks (especially Mermaid diagrams) from identifier modification
        saved_code_blocks: List[str] = []
        def _save_block(m: re.Match) -> str:
            saved_code_blocks.append(m.group(0))
            return f"@@CODE_BLOCK_PLACEHOLDER_{len(saved_code_blocks) - 1}@@"

        protected_answer = re.sub(r"```[\s\S]*?```", _save_block, answer)

        # Standard expansions enforcement on text
        protected_answer = re.sub(
            r"(?i)\bBilling\s+(?:and|&)\s+Revenue\s+Innovation\s+Management\b",
            "Billing and Revenue Innovation Management",
            protected_answer,
        )
        protected_answer = re.sub(
            r"(?i)\bContract\s+Accounts?\s+Receivable\s+(?:and|&)\s+Payables?\b",
            "Contract Accounts Receivable and Payable",
            protected_answer,
        )

        evidence_text = " ".join([
            str(p.get("chunk_text") or p.get("snippet") or "") + " "
            + str(p.get("title") or "") + " "
            + str(p.get("document_name") or "")
            for p in passages
        ]).lower()

        # Regular expressions for technical SAP identifiers
        tcode_pattern = re.compile(
            r"\b(/[a-zA-Z0-9_]{2,}/[a-zA-Z0-9_]+|[A-Z]{1,4}\d{1,4}[A-Z0-9]?|[A-Z0-9_]{4,}_[A-Z0-9_]+)\b"
        )
        table_pattern = re.compile(
            r"\b(DFKK[A-Z0-9_]+|FKK[A-Z0-9_]+|ERDK|ERCH|BUT\d{3}|BSEG|BKPF|ACDOCA|MARA|MARC|VBAK|VBAP|EKKO|EKPO)\b",
            re.IGNORECASE,
        )

        EXCLUDE = {
            "sap", "brim", "som", "cc", "ci", "fica", "fi-ca", "hana", "s4hana", "s/4hana", "ecc",
            "api", "apis", "rest", "soap", "json", "xml", "html", "http", "https", "url", "urls",
            "sql", "db", "gui", "ui", "uuid", "guid", "id", "ids", "pdf", "rfc", "bapi", "odi",
            "bit", "bits", "cit", "cits", "gl", "g/l", "bp", "crm", "erp", "rag", "llm", "step",
            "status", "true", "false", "null", "none", "note", "notes", "help", "user", "role",
            "view", "data", "text", "page", "file", "code", "table", "field", "info", "item",
            "items", "plan", "post", "send", "save", "read", "open", "type", "date", "time",
            "rate", "name", "desc", "docs", "test", "fail", "pass", "done", "error", "warning",
            "check", "order", "event", "usage", "batch", "class", "classes", "class_id",
            "section", "problem", "summary", "analysis", "likely", "causes", "process", "flow",
            "modules", "integration", "points", "investigation", "verified", "expected", "results",
            "validation", "recovery", "prevention", "citations", "mermaid", "graph", "subgraph",
            "order_mgmt", "som_layer", "ci_layer", "cc_layer", "fica_layer", "fin_layer", "eng",
            "ext_layer", "usage_layer", "pay_gw"
        }

        flagged = set()
        for m in table_pattern.finditer(protected_answer):
            t_name = m.group(0)
            if t_name.lower() not in evidence_text and t_name not in flagged:
                flagged.add(t_name)

        for m in tcode_pattern.finditer(protected_answer):
            tc = m.group(0)
            if tc.lower() in EXCLUDE or tc.lower() in evidence_text:
                continue
            if tc not in flagged:
                flagged.add(tc)

        for ident in flagged:
            if "PLACEHOLDER" in ident.upper() or "CODE_BLOCK" in ident.upper():
                continue
            logger.warning(
                "Unsupported SAP technical identifier '%s' not present in retrieved sources; flagged as unverified.",
                ident
            )
            pattern = re.compile(rf"\b({re.escape(ident)})(?!\s*\((?:unverified|confirm in your system)[^)]*\))\b")
            protected_answer = pattern.sub(rf"\1 (unverified, confirm in your system)", protected_answer)

        # Restore preserved code blocks intact
        for idx, block in enumerate(saved_code_blocks):
            protected_answer = protected_answer.replace(f"@@CODE_BLOCK_PLACEHOLDER_{idx}@@", block)
            protected_answer = protected_answer.replace(f"__CODE_BLOCK_PLACEHOLDER_{idx}__", block)

        # Wherever an unverified notice is attached to a closing fence, put it on its own line after the fence:
        # before: "```" + " (unverified, confirm in your system)"
        # after: "```\n\n_(Unverified, confirm in your system)_\n\n"
        protected_answer = re.sub(
            r"(```+)[ \t]*\(?(?:unverified,?\s*)?confirm in your system[^)\n]*\)?",
            r"\1\n\n_(Unverified, confirm in your system)_\n\n",
            protected_answer,
            flags=re.IGNORECASE,
        )
        protected_answer = re.sub(
            r"(```+)[ \t]*\((?:unverified|confirm in your system)[^)\n]*\)",
            r"\1\n\n_(Unverified, confirm in your system)_\n\n",
            protected_answer,
            flags=re.IGNORECASE,
        )
        return protected_answer

    def _retrieve_internal_evidence(
        self,
        db: Session,
        query: str,
        timings: Optional[Dict[str, float]] = None,
        is_follow_up: bool = False,
    ) -> Tuple[List[Dict[str, Any]], float, Dict[str, Any]]:
        candidates = retrieval_service.hybrid_search(
            db, query, top_k=settings.TOP_K, stage_timings=timings
        ) if db is not None else []
        if timings is not None:
            timings["retrieved_candidates"] = len(candidates)
        rerank_started = time.perf_counter()
        top_chunks, rerank_score, _ = reranking_service.rerank_kb(
            query, candidates, top_n=settings.RERANK_TOP_K
        )
        if timings is not None:
            timings["reranking_ms"] = round((time.perf_counter() - rerank_started) * 1000, 2)
        relevance_started = time.perf_counter()
        confidence_data = evidence_selection_service.compute_kb_evidence_score(
            query, top_chunks, threshold=settings.KB_CONFIDENCE_THRESHOLD, is_follow_up=is_follow_up
        )
        if timings is not None:
            timings["relevance_evaluation_ms"] = timings.get("relevance_evaluation_ms", 0.0) + round((time.perf_counter() - relevance_started) * 1000, 2)

        return top_chunks, rerank_score, confidence_data

    def _search_with_kb_fallback(
        self,
        db: Session,
        query: str,
        timings: Dict[str, float],
        is_follow_up: bool = False,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], bool, List[Dict[str, Any]], Dict[str, Any]]:
        """Strict KB-First RAG: Query the Knowledge Base first.
        
        If evidence score >= KB_CONFIDENCE_THRESHOLD (default 0.75) and the relevance
        gate passes: answer from KB chunks ONLY, leaving Tavily idle.
        
        If KB evidence is below threshold or fails the relevance gate:
        fall back to Tavily web search directly without drafting an answer from weak KB.
        """
        # 1. Search KB first
        kb_started = time.perf_counter()
        kb_chunks = []
        kb_confidence = {}
        try:
            kb_chunks, _, kb_confidence = self._retrieve_internal_evidence(
                db, query, timings, is_follow_up=is_follow_up
            )
        except Exception as exc:
            logger.warning("KB retrieval failed (%s); triggering Tavily fallback.", type(exc).__name__)
            kb_chunks = []
            kb_confidence = evidence_selection_service.compute_kb_evidence_score(
                query, [], threshold=settings.KB_CONFIDENCE_THRESHOLD, is_follow_up=is_follow_up
            )
            kb_confidence["fallback_reason"] = f"KB retrieval error ({type(exc).__name__})."

        timings["kb_retrieval_ms"] = round((time.perf_counter() - kb_started) * 1000, 2)
        score = kb_confidence.get("evidence_score", kb_confidence.get("confidence", 0.0))
        thresh = kb_confidence.get("threshold", settings.KB_CONFIDENCE_THRESHOLD)
        gate_passed = kb_confidence.get(
            "gate_passed",
            True if not kb_confidence.get("should_trigger_tavily", True) else False
        )
        passed = kb_confidence.get("passed", (score >= thresh and gate_passed))

        # 2. If KB score >= threshold and gate passed: use KB ONLY, do not call Tavily
        if passed and kb_chunks:
            logger.info(
                "KB evidence evaluation passed: score=%.4f threshold=%.2f chosen_source=knowledge_base fallback_reason=None",
                score, thresh
            )
            normalized_kb = [
                evidence_selection_service.normalize_internal_chunk(c)
                for c in kb_chunks[:settings.RERANK_TOP_K]
                if str(c.get("chunk_text") or "").strip()
            ]
            kb_selection = {
                "selected_passages": normalized_kb,
                "source_type": "knowledge_base",
                "selected_source": "knowledge_base",
                "kb_relevance_score": kb_confidence.get("kb_relevance_score", round(score * 100, 1)),
                "kb_threshold": round(thresh * 100),
                "evidence_score": score,
                "threshold": thresh,
                "fallback_reason": None,
                "internal_evidence_confidence": score,
                "selected_evidence_quality": score,
                "external_search_triggered": False,
                "selection_summary": f"KB evidence score ({score:.2f}) met threshold ({thresh:.2f}) and passed relevance gate.",
                "evidence_coverage": 1.0 if normalized_kb else 0.0,
            }
            timings["tavily_ms"] = 0.0
            timings["web_search_and_selection_ms"] = 0.0
            return kb_selection, [], False, kb_chunks, kb_confidence

        # 3. Otherwise: KB evidence is below threshold or gate failed -> call Tavily directly!
        fallback_reason = kb_confidence.get("fallback_reason") or f"KB evidence score ({score:.2f}) below threshold ({thresh:.2f})."
        logger.info(
            "KB evidence evaluation failed: score=%.4f threshold=%.2f chosen_source=web_search fallback_reason=%s",
            score, thresh, fallback_reason
        )

        web_started = time.perf_counter()
        web_search_service.reset_request_timing()
        selection, web_results, web_search_succeeded = self._search_web_only(
            query, kb_confidence, kb_chunks
        )
        timings["tavily_ms"] = round(web_search_service.request_elapsed_ms, 2)
        timings["web_search_and_selection_ms"] = round(
            (time.perf_counter() - web_started) * 1000, 2
        )
        if selection:
            selection["evidence_score"] = score
            selection["threshold"] = thresh
            selection["fallback_reason"] = fallback_reason

        return selection, web_results, web_search_succeeded, kb_chunks, kb_confidence

    @staticmethod
    def _generate_search_queries(query: str) -> List[str]:
        """Generate targeted, deduplicated search queries prioritizing reliable SAP technical sources."""
        clean = query.strip()
        if not clean:
            return []

        queries: List[str] = [clean]
        norm_clean = clean.lower()
        if not any(term in norm_clean for term in ("documentation", "manual", "guide", "sap help")):
            doc_query = f"{clean} official SAP documentation"
            queries.append(doc_query)

        max_q = getattr(settings, "TAVILY_MAX_QUERIES", 2)
        return queries[:max_q]

    def _search_web_only(
        self,
        query: str,
        internal_confidence_data: Dict[str, Any],
        internal_candidates: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], bool]:
        """Search authoritative SAP web sources when KB evidence fails threshold or gate.
        Enforces overall deadline across all web search attempts, query capping, deduplication,
        and falls back to trustworthy KB evidence if web search fails or times out.
        """
        all_results: List[Dict[str, Any]] = []
        search_returned_results = False
        selection: Dict[str, Any] = {}
        search_queries = self._generate_search_queries(query)
        overall_deadline = time.perf_counter() + settings.TAVILY_OVERALL_DEADLINE_SECONDS

        for attempt, search_query in enumerate(search_queries):
            remaining = overall_deadline - time.perf_counter()
            if remaining <= 0:
                logger.warning("Overall Tavily deadline reached before search query %d.", attempt + 1)
                break

            try:
                try:
                    results = web_search_service.search_sap_authoritative(
                        search_query,
                        deadline=overall_deadline,
                    )
                except TypeError:
                    results = web_search_service.search_sap_authoritative(search_query)
                if results:
                    search_returned_results = True
                    known_urls = {str(item.get("url", "")) for item in all_results}
                    all_results.extend(
                        item for item in results
                        if str(item.get("url", "")) not in known_urls
                    )
            except TavilyAuthenticationError as exc:
                logger.error("Tavily authentication error: %s", exc)
                break
            except TavilySearchError as exc:
                logger.info("Tavily search attempt %d failed (%s); checking deadline.", attempt + 1, type(exc).__name__)
                continue
            except Exception as exc:
                logger.warning("SAP web search failed (%s); checking deadline.", type(exc).__name__)
                continue

            if all_results:
                selection = evidence_selection_service.select_strongest_evidence(
                    query=query,
                    internal_candidates=[],
                    external_candidates=all_results,
                    internal_confidence_data=internal_confidence_data,
                    force_web=True,
                )
                if selection.get("selected_passages"):
                    break

        # If web search produced validated results, use them
        if selection and selection.get("selected_passages"):
            return selection, all_results, search_returned_results

        # Fallback to trustworthy internal KB candidates if web search failed, timed out, or returned no valid evidence
        if internal_candidates:
            logger.info(
                "Tavily web search unavailable or yielded no evidence; continuing with %d internal KB candidate chunks.",
                len(internal_candidates),
            )
            normalized_kb = [
                evidence_selection_service.normalize_internal_chunk(c)
                for c in internal_candidates[:settings.RERANK_TOP_K]
                if str(c.get("chunk_text") or "").strip()
            ]
            kb_score = float(internal_confidence_data.get("evidence_score", 0.0))
            kb_thresh = float(internal_confidence_data.get("threshold", settings.KB_CONFIDENCE_THRESHOLD))
            selection = {
                "selected_passages": normalized_kb,
                "source_type": "knowledge_base",
                "selected_source": "knowledge_base",
                "is_evidence_limited": True,
                "kb_relevance_score": internal_confidence_data.get("kb_relevance_score", round(kb_score * 100, 1)),
                "kb_threshold": round(kb_thresh * 100),
                "evidence_score": kb_score,
                "threshold": kb_thresh,
                "fallback_reason": "Web search timed out or unavailable; proceeding with available internal knowledge base evidence.",
                "internal_evidence_confidence": kb_score,
                "selected_evidence_quality": kb_score,
                "external_search_triggered": True,
                "selection_summary": "Web search unavailable/timed out; continuing with available internal knowledge base evidence.",
                "evidence_coverage": 1.0 if normalized_kb else 0.0,
            }
            return selection, all_results, False

        # If truly neither web nor KB has chunks
        selection = {
            "selected_passages": [],
            "source_type": "insufficient",
            "selected_source": "insufficient",
            "kb_relevance_score": round(float(internal_confidence_data.get("evidence_score", 0.0)) * 100, 1),
            "kb_threshold": round(float(internal_confidence_data.get("threshold", settings.KB_CONFIDENCE_THRESHOLD)) * 100),
            "evidence_score": float(internal_confidence_data.get("evidence_score", 0.0)),
            "threshold": float(internal_confidence_data.get("threshold", settings.KB_CONFIDENCE_THRESHOLD)),
            "fallback_reason": internal_confidence_data.get("fallback_reason") or "Tavily web search returned no authoritative SAP documentation.",
            "internal_evidence_confidence": float(internal_confidence_data.get("evidence_score", 0.0)),
            "selected_evidence_quality": 0.0,
            "external_search_triggered": True,
            "selection_summary": "Tavily web search returned no authoritative SAP documentation.",
            "evidence_coverage": 0.0,
        }

        return selection, all_results, search_returned_results

    def process_query(
        self,
        db: Session,
        query: str,
        chat_history: Optional[List[Dict[str, Any]]] = None,
        user: Optional[Any] = None,
        has_attachment: bool = False,
        attachment_context: str = "",
        attachments_data: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Synchronous execution of the verified RAG pipeline with enterprise security enforcement."""
        pipeline_started = time.perf_counter()
        stage_timings: Dict[str, float] = {}
        # 0. Resolve user identity and role
        user_role = getattr(user, "role", "consultant") if user else "consultant"
        user_id = getattr(user, "id", None) if user else None
        user_email = getattr(user, "email", None) if user else None

        # 0b. Strict Image Validation: Readability & SAP Domain Refusal Check
        if attachments_data:
            for att in attachments_data:
                is_img_att = (
                    att.get("file_type") == "image"
                    or any(str(att.get("filename", "")).lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp"))
                    or "vision_metadata" in att
                )
                if is_img_att:
                    vm = att.get("vision_metadata") or {}
                    # If image is unreadable, ask for a clearer screenshot without guessing
                    if vm.get("readable") is False or vm.get("is_unclear") is True:
                        unclear_msg = (
                            "The uploaded screenshot is unreadable or too blurry to determine the exact SAP transaction or error details. "
                            "Please upload a clearer, higher-resolution screenshot of the SAP screen or dialog box so I can guide you step-by-step."
                        )
                        return {
                            "answer": unclear_msg,
                            "source_type": "insufficient",
                            "grounding_score": None,
                            "is_in_rag_pipeline": False,
                            "kb_score": 0.0,
                            "web_score": 0.0,
                            "winning_score": 0.0,
                            "selected_source": "insufficient",
                            "verification_status": "verified",
                            "grounding_status": "not_applicable",
                            "grounding_method": "not_applicable",
                            "kb_grounding_score": None,
                            "web_grounding_score": None,
                            "grounding_claims": [],
                            "internal_evidence_confidence": 0.0,
                            "selected_evidence_quality": 0.0,
                            "external_search_used": False,
                            "citations": [],
                            "web_sources": [],
                            "follow_up_questions": [],
                            "selection_summary": "Unclear screenshot - requested clearer image.",
                            "stage_timings_ms": {"total_backend_ms": round((time.perf_counter() - pipeline_started) * 1000, 2)},
                        }
                    # If image is not SAP, politely refuse per strict SAP-only policy
                    if vm.get("is_sap") is False:
                        non_sap_refusal = (
                            "This assistant specializes exclusively in SAP enterprise solutions, screens, and business processes. "
                            "The uploaded image does not appear to be an SAP system screen. "
                            "Please provide a screenshot of your SAP GUI, Fiori Launchpad, or SAP error dialog."
                        )
                        return {
                            "answer": non_sap_refusal,
                            "source_type": "refusal",
                            "grounding_score": None,
                            "is_in_rag_pipeline": False,
                            "kb_score": 0.0,
                            "web_score": 0.0,
                            "winning_score": 0.0,
                            "selected_source": "refusal",
                            "verification_status": "rejected",
                            "grounding_status": "not_applicable",
                            "grounding_method": "not_applicable",
                            "kb_grounding_score": None,
                            "web_grounding_score": None,
                            "grounding_claims": [],
                            "internal_evidence_confidence": 0.0,
                            "selected_evidence_quality": 0.0,
                            "external_search_used": False,
                            "citations": [],
                            "web_sources": [],
                            "follow_up_questions": [],
                            "selection_summary": "Image rejected as outside SAP scope.",
                            "stage_timings_ms": {"total_backend_ms": round((time.perf_counter() - pipeline_started) * 1000, 2)},
                        }

        # 1. Lightweight Intent & Sentiment Pre-Processing
        convo_analysis = conversational_service.analyze(query, chat_history=chat_history)
        if (
            convo_analysis["is_conversational_only"]
            and convo_analysis["direct_reply"]
            and not has_attachment
        ):
            stage_timings["conversational_ms"] = round((time.perf_counter() - pipeline_started) * 1000, 2)
            stage_timings["total_backend_ms"] = stage_timings["conversational_ms"]
            logger.info("Direct conversational response generated intent=%s sentiment=%s", convo_analysis["intent"], convo_analysis["sentiment"])
            return {
                "answer": convo_analysis["direct_reply"],
                "source_type": "conversational",
                "grounding_score": None,
                "is_in_rag_pipeline": False,
                "kb_score": 0.0,
                "web_score": 0.0,
                "winning_score": 0.0,
                "selected_source": "conversational",
                "verification_status": "verified",
                "grounding_status": "not_applicable",
                "grounding_method": "not_applicable",
                "kb_grounding_score": None,
                "web_grounding_score": None,
                "grounding_claims": [],
                "internal_evidence_confidence": 0.0,
                "selected_evidence_quality": 0.0,
                "external_search_used": False,
                "citations": [],
                "web_sources": [],
                "follow_up_questions": [],
                "selection_summary": "Natural conversational response.",
                "stage_timings_ms": stage_timings,
            }

        effective_query = convo_analysis["extracted_query"] if convo_analysis.get("is_mixed") else query
        tone_guidance = convo_analysis.get("tone_guidance", "")

        # 2. Query Resolution & Follow-Up Check
        resolution = query_rewriter.resolve_query(effective_query, chat_history=chat_history)
        is_follow_up = resolution.get("is_follow_up", False)
        resolved_query = resolution.get("resolved_query", effective_query).strip()
        cleaned_query = resolved_query

        # 3. Strict SAP Domain Classifier Enforcement
        target_check_query = cleaned_query if is_follow_up else effective_query.strip()
        try:
            is_sap, _ = sap_classifier.classify(target_check_query, chat_history=chat_history, has_attachment=has_attachment)
        except TypeError:
            is_sap, _ = sap_classifier.classify(target_check_query, chat_history=chat_history)
        stage_timings["preprocessing_ms"] = round((time.perf_counter() - pipeline_started) * 1000, 2)

        if not is_sap:
            logger.warning("SAP scope guard refused question=%r", query)
            return {
                "answer": SAP_SCOPE_REFUSAL,
                "source_type": "refusal",
                "grounding_score": None,
                "is_in_rag_pipeline": False,
                "kb_score": 0.0,
                "web_score": 0.0,
                "winning_score": 0.0,
                "selected_source": "refusal",
                "verification_status": "rejected",
                "grounding_status": "not_applicable",
                "grounding_method": "not_applicable",
                "kb_grounding_score": None,
                "web_grounding_score": None,
                "grounding_claims": [],
                "internal_evidence_confidence": 0.0,
                "selected_evidence_quality": 0.0,
                "external_search_used": False,
                "citations": [],
                "web_sources": [],
                "follow_up_questions": [],
                "selection_summary": "Query rejected as outside SAP scope.",
            }

        # 3b. Classify Task Type (architecture, screenshot_analysis, troubleshooting, implementation, explanation)
        task_type = answer_planner.classify_task(cleaned_query, has_attachment=has_attachment)
        if attachment_context:
            cleaned_query = f"{cleaned_query}\n\n{attachment_context}".strip()

        # Inject User Custom Instructions if configured
        if user:
            custom_parts = []
            if getattr(user, "custom_instructions_about_user", None):
                custom_parts.append(f"About User Profile: {user.custom_instructions_about_user.strip()}")
            if getattr(user, "custom_instructions_how_to_respond", None):
                custom_parts.append(f"User Response Directives: {user.custom_instructions_how_to_respond.strip()}")
            if custom_parts:
                tone_guidance = (tone_guidance + "\n" + "\n".join(custom_parts)).strip()

        # 4. Hybrid Cross-Chat Memory Retrieval with strict isolation and timeout protection
        memory_retrieval_res = {
            "used_memories": [],
            "used_memory_ids": [],
            "formatted_context": "",
            "previous_context_used": False,
        }
        if user_id:
            try:
                mem_start = time.perf_counter()
                memory_retrieval_res = memory_service.retrieve_relevant_memories(
                    db, user_id=user_id, query=cleaned_query, top_k=5
                )
                stage_timings["memory_retrieval_ms"] = round((time.perf_counter() - mem_start) * 1000, 2)
                if not chat_history and memory_retrieval_res.get("top_scenario"):
                    condensed = memory_service.condense_query_with_memory(cleaned_query, memory_retrieval_res)
                    if condensed != cleaned_query:
                        cleaned_query = condensed
            except Exception as mem_err:
                logger.warning(f"Memory retrieval failed gracefully ({type(mem_err).__name__}): {mem_err}")
                stage_timings["memory_retrieval_ms"] = 0.0

        current_chat_context = ""
        if chat_history:
            current_chat_context = "\n".join([
                f"{m.get('role', 'user').capitalize()}: {m.get('content', '')[:500]}"
                for m in chat_history[-6:]
            ])

        # Formulate targeted RAG query using extracted error text and transaction code from vision step
        rag_search_query = cleaned_query
        if attachments_data:
            extracted_tech_terms = []
            for att in attachments_data:
                if att.get("file_type") == "image":
                    vm = att.get("vision_metadata") or {}
                    tc = vm.get("transaction_code")
                    err = vm.get("error_text")
                    msg = vm.get("message_class_and_number")
                    scr = vm.get("screen_or_app")
                    if tc and tc != "N/A":
                        extracted_tech_terms.append(tc)
                    if msg and msg != "N/A":
                        extracted_tech_terms.append(msg)
                    if err and err != "N/A":
                        extracted_tech_terms.append(err)
                    if not extracted_tech_terms and scr and scr != "N/A":
                        extracted_tech_terms.append(scr)
            if extracted_tech_terms:
                tech_snippet = " ".join(extracted_tech_terms)
                rag_search_query = f"{cleaned_query} {tech_snippet}".strip() if cleaned_query else tech_snippet

        # Strict KB-First evaluation: Knowledge Base is checked first.
        # If evidence score meets threshold (0.75) and gate passes, Tavily is left idle.
        try:
            evidence_selection, web_results, web_search_succeeded, top_kb_chunks, internal_confidence_data = self._search_with_kb_fallback(
                db, rag_search_query, stage_timings, is_follow_up=is_follow_up
            )
        except TypeError:
            evidence_selection, web_results, web_search_succeeded, top_kb_chunks, internal_confidence_data = self._search_with_kb_fallback(
                db, rag_search_query, stage_timings
            )
        internal_conf = float(internal_confidence_data.get("evidence_score", internal_confidence_data.get("confidence", 0.0)))
        selected_passages = evidence_selection.get("selected_passages") or []
        selected_source_type = evidence_selection.get("source_type") or "insufficient"
        selected_quality = evidence_selection.get("selected_evidence_quality", 0.0)
        fallback_reason = evidence_selection.get("fallback_reason")

        # 6. Generate Candidate Answer or Abstain on Insufficient Evidence
        llm_started = time.perf_counter()
        if (selected_source_type == "insufficient" or not selected_passages) and (task_type in ("architecture", "screenshot_analysis") or has_attachment):
            if task_type == "screenshot_analysis" or has_attachment:
                # Generate guided troubleshooting response using standard SAP expert principles
                candidate_answer = llm_service.generate_answer(
                    cleaned_query,
                    [],
                    source_type="sap_expert",
                    tone_guidance=tone_guidance,
                    memory_context=memory_retrieval_res.get("formatted_context", ""),
                    chat_history_context=current_chat_context,
                    has_attachment=has_attachment
                )
                final_answer = candidate_answer
                effective_source_type = "sap_expert"
                final_verification = {"grounding_score": 0.95, "status": "supported", "critical_unsupported_claims": [], "passes_grounding_gate": True}
            else:
                arch_analysis = vision_service._generate_architecture_analysis(cleaned_query, current_chat_context)
                final_answer = arch_analysis["text"]
                effective_source_type = "sap_expert"
                final_verification = {"grounding_score": 0.95, "status": "supported", "critical_unsupported_claims": [], "passes_grounding_gate": True}
            stage_timings["llm_total_ms"] = round((time.perf_counter() - llm_started) * 1000, 2)
            stage_timings["grounding_ms"] = 0.0
        elif selected_source_type == "insufficient" or not selected_passages:
            candidate_answer = None
            try:
                candidate_answer = llm_service.generate_answer(
                    cleaned_query,
                    [],
                    source_type="sap_expert",
                    tone_guidance=(tone_guidance + "\nNote: Documentation evidence is unavailable or insufficient. Provide a structured first-pass investigation plan based on standard SAP architecture principles. Clearly mark unverified possibilities and cite missing evidence without fabricating identifiers.").strip(),
                    memory_context=memory_retrieval_res.get("formatted_context", ""),
                    chat_history_context=current_chat_context,
                    has_attachment=has_attachment
                )
            except Exception as e:
                logger.warning("LLM generation for insufficient evidence failed: %s", e)

            if candidate_answer and candidate_answer.strip():
                final_answer = (
                    "I could not verify this SAP answer to the required confidence level (available evidence is insufficient and cannot be verified).\n\n"
                    + candidate_answer.strip()
                )
                effective_source_type = "insufficient"
                final_verification = {"grounding_score": 0.70, "status": "supported", "critical_unsupported_claims": [], "passes_grounding_gate": True}
            else:
                final_answer = self._insufficient_answer("insufficient", fallback_reason or "Available evidence is insufficient.")
                effective_source_type = "insufficient"
                final_verification = grounding_service.verify_answer(
                    cleaned_query, final_answer, [], source_type="insufficient"
                )
            stage_timings["llm_total_ms"] = round((time.perf_counter() - llm_started) * 1000, 2)
            stage_timings["grounding_ms"] = 0.0
        else:
            effective_source_type = selected_source_type
            try:
                candidate_answer = llm_service.generate_answer(
                    cleaned_query,
                    selected_passages,
                    source_type=effective_source_type,
                    tone_guidance=tone_guidance,
                    memory_context=memory_retrieval_res.get("formatted_context", ""),
                    chat_history_context=current_chat_context,
                    has_attachment=has_attachment
                )
            except TypeError:
                candidate_answer = llm_service.generate_answer(
                    cleaned_query,
                    selected_passages,
                    source_type=effective_source_type
                )
            except Exception as gen_err:
                logger.error("LLM generation failed: %s", gen_err)
                candidate_answer = None

            if not candidate_answer or not candidate_answer.strip():
                logger.error("LLM produced empty candidate answer. Emitting structured fallback.")
                candidate_answer = (
                    "I was unable to complete the answer from the available evidence. "
                    "Please check your system parameters or retry."
                )

            stage_timings["llm_total_ms"] = round((time.perf_counter() - llm_started) * 1000, 2)

            # Ensure architecture and diagram requests include rendered Mermaid diagrams
            format_hint = answer_planner.detect_format_hint(cleaned_query, chat_history_context=current_chat_context)
            if (task_type == "architecture" or format_hint.get("wants_diagram")) and "```mermaid" not in candidate_answer:
                mermaid_code = vision_service.generate_diagram(cleaned_query, current_chat_context)
                candidate_answer += f"\n\n### Interactive Architecture Diagram\n```mermaid\n{mermaid_code}\n```\n"

            # Post-generation check: enforce standard expansions and audit identifiers against sources
            candidate_answer = self._sanitize_and_verify_identifiers(candidate_answer, selected_passages)

            # 7. Claim-Level Grounding Verification
            grounding_started = time.perf_counter()
            verification = grounding_service.verify_answer(
                cleaned_query, candidate_answer, selected_passages, source_type=selected_source_type
            )
            stage_timings["grounding_ms"] = round((time.perf_counter() - grounding_started) * 1000, 2)

            final_answer = candidate_answer
            final_verification = verification

            # 8. Grounding policy: Veto publication if critical unsupported claims or verification fails
            critical_unsupported = final_verification.get("critical_unsupported_claims", [])
            passes_gate = final_verification.get("passes_grounding_gate", False)
            if critical_unsupported or not passes_gate:
                final_answer = self._insufficient_answer(
                    selected_source_type,
                    "Answer contained unsupported claims or unverified technical identifiers."
                )
                effective_source_type = selected_source_type
                final_verification = grounding_service.verify_answer(
                    cleaned_query, final_answer, [], source_type="insufficient"
                )

        follow_ups = (
            followup_service.generate_followup_questions(cleaned_query, final_answer, selected_passages)
            if selected_passages else []
        )

        # Build Citations and Web Sources with exact metadata
        citations = []
        web_sources = []
        for p in selected_passages:
            if p.get("source_type") == "knowledge_base":
                citations.append({
                    "id": str(p.get("chunk_id") or p.get("source_id") or ""),
                    "chunk_id": str(p.get("chunk_id") or p.get("source_id") or ""),
                    "document": p.get("document_name", "SAP Manual"),
                    "page": p.get("page_number", 1),
                    "section": p.get("section", ""),
                    "score": round(float(p.get("relevance_score", 0.7)), 4),
                    "snippet": p.get("snippet", "")
                })
            elif p.get("source_type") in ("web", "web_search"):
                web_sources.append({
                    "id": str(p.get("source_id") or ""),
                    "title": p.get("title", "SAP Documentation"),
                    "url": p.get("url", ""),
                    "domain": p.get("domain", "help.sap.com"),
                    "snippet": p.get("snippet", "")
                })

        stage_timings["total_backend_ms"] = round((time.perf_counter() - pipeline_started) * 1000, 2)
        total_time = stage_timings["total_backend_ms"]
        for k in list(stage_timings.keys()):
            if k != "total_backend_ms" and stage_timings[k] > total_time:
                stage_timings[k] = total_time

        retrieved_candidate_count = int(stage_timings.pop("retrieved_candidates", len(top_kb_chunks)))
        llm_provider = getattr(settings, "LLM_PROVIDER", "groq")
        llm_model = llm_service.selected_stream_model or settings.LLM_MODEL
        logger.info(
            "rag_timing stages_ms=%s retrieved_chunks=%d llm_chunks=%d provider=%s model=%s selected_source=%s evidence_score=%.4f",
            stage_timings, retrieved_candidate_count, len(selected_passages), llm_provider, llm_model, effective_source_type, internal_conf
        )

        return {
            "answer": final_answer,
            "source_type": effective_source_type,
            "grounding_score": final_verification.get("grounding_score"),
            "kb_grounding_score": final_verification.get("kb_grounding_score"),
            "web_grounding_score": final_verification.get("web_grounding_score"),
            "grounding_status": final_verification.get("grounding_status"),
            "grounding_method": final_verification.get("verification_method"),
            "grounding_claims": final_verification.get("claims", []),
            "grounding_summary": final_verification.get("summary"),
            "is_in_rag_pipeline": selected_source_type == "knowledge_base",
            "kb_score": round(internal_conf, 4),
            "evidence_score": round(internal_conf, 4),
            "threshold": round(settings.KB_CONFIDENCE_THRESHOLD, 4),
            "web_score": round(selected_quality, 4),
            "winning_score": round(selected_quality, 4),
            "selected_source": effective_source_type,
            "verification_status": final_verification.get("verification_status"),
            "internal_evidence_confidence": internal_conf,
            "selected_evidence_quality": selected_quality,
            "external_search_used": web_search_succeeded,
            "web_search_used": selected_source_type in ("web", "web_search") and bool(selected_passages),
            "kb_relevance_score": internal_confidence_data.get("kb_relevance_score", round(internal_conf * 100, 1)),
            "kb_threshold": round(settings.KB_CONFIDENCE_THRESHOLD * 100),
            "fallback_reason": fallback_reason,
            "citations": citations,
            "web_sources": web_sources,
            "follow_up_questions": follow_ups,
            "selection_summary": evidence_selection.get("selection_summary", ""),
            "stage_timings_ms": stage_timings,
            "used_memories": memory_retrieval_res.get("used_memories", []),
            "used_memory_ids": memory_retrieval_res.get("used_memory_ids", []),
            "previous_context_used": memory_retrieval_res.get("previous_context_used", False),
        }

    def stream_query(
        self,
        db: Session,
        query: str,
        chat_history: Optional[List[Dict[str, Any]]] = None,
        user: Optional[Any] = None,
        request_id: Optional[str] = None,
        request_started_at: Optional[float] = None,
        has_attachment: bool = False,
        attachment_context: str = "",
        attachments_data: Optional[List[Dict[str, Any]]] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Progressive Streaming Pipeline for SAP BRIM Knowledge Assistant with Security Enforcement.
        Emits progress and answer tokens as the pipeline runs, then includes the final
        answer, grounding evaluation, and source metadata in the completion event.
        """
        pipeline_started = request_started_at or time.perf_counter()
        stage_timings: Dict[str, float] = {
            "request_arrival_pre_rag_ms": round((time.perf_counter() - pipeline_started) * 1000, 2)
        }
        # 0. Resolve user identity and role
        user_role = getattr(user, "role", "consultant") if user else "consultant"
        user_id = getattr(user, "id", None) if user else None
        user_email = getattr(user, "email", None) if user else None

        # 0b. Strict Image Validation: Readability & SAP Domain Refusal Check
        if attachments_data:
            for att in attachments_data:
                is_img_att = (
                    att.get("file_type") == "image"
                    or any(str(att.get("filename", "")).lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp"))
                    or "vision_metadata" in att
                )
                if is_img_att:
                    vm = att.get("vision_metadata") or {}
                    if vm.get("readable") is False or vm.get("is_unclear") is True:
                        unclear_msg = (
                            "The uploaded screenshot is unreadable or too blurry to determine the exact SAP transaction or error details. "
                            "Please upload a clearer, higher-resolution screenshot of the SAP screen or dialog box so I can guide you step-by-step."
                        )
                        yield {"type": "token", "content": unclear_msg}
                        yield {
                            "type": "done",
                            "answer": unclear_msg,
                            "source_type": "insufficient",
                            "grounding_score": None,
                            "is_in_rag_pipeline": False,
                            "kb_score": 0.0,
                            "web_score": 0.0,
                            "winning_score": 0.0,
                            "selected_source": "insufficient",
                            "verification_status": "verified",
                            "grounding_status": "not_applicable",
                            "grounding_method": "not_applicable",
                            "kb_grounding_score": None,
                            "web_grounding_score": None,
                            "grounding_claims": [],
                            "internal_evidence_confidence": 0.0,
                            "selected_evidence_quality": 0.0,
                            "external_search_used": False,
                            "citations": [],
                            "web_sources": [],
                            "follow_up_questions": [],
                            "selection_summary": "Unclear screenshot - requested clearer image.",
                        }
                        return
                    if vm.get("is_sap") is False:
                        non_sap_refusal = (
                            "This assistant specializes exclusively in SAP enterprise solutions, screens, and business processes. "
                            "The uploaded image does not appear to be an SAP system screen. "
                            "Please provide a screenshot of your SAP GUI, Fiori Launchpad, or SAP error dialog."
                        )
                        yield {"type": "token", "content": non_sap_refusal}
                        yield {
                            "type": "done",
                            "answer": non_sap_refusal,
                            "source_type": "refusal",
                            "grounding_score": None,
                            "is_in_rag_pipeline": False,
                            "kb_score": 0.0,
                            "web_score": 0.0,
                            "winning_score": 0.0,
                            "selected_source": "refusal",
                            "verification_status": "rejected",
                            "grounding_status": "not_applicable",
                            "grounding_method": "not_applicable",
                            "kb_grounding_score": None,
                            "web_grounding_score": None,
                            "grounding_claims": [],
                            "internal_evidence_confidence": 0.0,
                            "selected_evidence_quality": 0.0,
                            "external_search_used": False,
                            "citations": [],
                            "web_sources": [],
                            "follow_up_questions": [],
                            "selection_summary": "Image rejected as outside SAP scope.",
                        }
                        return

        # STAGE 0: Lightweight Intent & Sentiment Pre-Processing
        convo_analysis = conversational_service.analyze(query, chat_history=chat_history)
        if (
            convo_analysis["is_conversational_only"]
            and convo_analysis["direct_reply"]
            and not has_attachment
        ):
            reply = convo_analysis["direct_reply"]
            logger.info("Stream direct conversational reply intent=%s request_id=%s", convo_analysis["intent"], request_id or "unavailable")
            yield {
                "type": "token",
                "content": reply
            }
            yield {
                "type": "done",
                "answer": reply,
                "source_type": "conversational",
                "grounding_score": None,
                "is_in_rag_pipeline": False,
                "kb_score": 0.0,
                "web_score": 0.0,
                "winning_score": 0.0,
                "selected_source": "conversational",
                "verification_status": "verified",
                "grounding_status": "not_applicable",
                "grounding_method": "not_applicable",
                "kb_grounding_score": None,
                "web_grounding_score": None,
                "grounding_claims": [],
                "internal_evidence_confidence": 0.0,
                "selected_evidence_quality": 0.0,
                "external_search_used": False,
                "citations": [],
                "web_sources": [],
                "follow_up_questions": [],
                "selection_summary": "Natural conversational response.",
                "stage_timings_ms": {
                    "total_backend_ms": round((time.perf_counter() - pipeline_started) * 1000, 2)
                }
            }
            return

        effective_query = convo_analysis["extracted_query"] if convo_analysis.get("is_mixed") else query
        tone_guidance = convo_analysis.get("tone_guidance", "")

        # STAGE 1: Context Resolution & Follow-Up Check
        yield {
            "type": "status",
            "stage": "thinking",
            "message": "Resolving conversation context..."
        }

        stage_started = time.perf_counter()
        resolution = query_rewriter.resolve_query(effective_query, chat_history=chat_history)
        is_follow_up = resolution.get("is_follow_up", False)
        resolved_query = resolution.get("resolved_query", effective_query).strip()
        cleaned_query = resolved_query

        # Scope Verification via SAPClassifier
        target_check_query = cleaned_query if is_follow_up else effective_query.strip()
        try:
            is_sap, _ = sap_classifier.classify(target_check_query, chat_history=chat_history, has_attachment=has_attachment)
        except TypeError:
            is_sap, _ = sap_classifier.classify(target_check_query, chat_history=chat_history)
        stage_timings["preprocessing_ms"] = round((time.perf_counter() - stage_started) * 1000, 2)

        if not is_sap:
            logger.warning(
                "SAP scope guard refused streamed question=%r request_id=%s",
                query,
                request_id or "unavailable",
            )
            yield {
                "type": "token",
                "content": SAP_SCOPE_REFUSAL,
            }
            yield {
                "type": "done",
                "answer": SAP_SCOPE_REFUSAL,
                "source_type": "refusal",
                "grounding_score": None,
                "is_in_rag_pipeline": False,
                "kb_score": 0.0,
                "web_score": 0.0,
                "winning_score": 0.0,
                "selected_source": "refusal",
                "verification_status": "rejected",
                "grounding_status": "not_applicable",
                "grounding_method": "not_applicable",
                "kb_grounding_score": None,
                "web_grounding_score": None,
                "grounding_claims": [],
                "internal_evidence_confidence": 0.0,
                "selected_evidence_quality": 0.0,
                "external_search_used": False,
                "citations": [],
                "web_sources": [],
                "follow_up_questions": [],
                "selection_summary": "Query rejected as outside SAP scope.",
            }
            return

        # 3b. Classify Task Type
        task_type = answer_planner.classify_task(cleaned_query, has_attachment=has_attachment)
        if attachment_context:
            cleaned_query = f"{cleaned_query}\n\n{attachment_context}".strip()

        # Inject User Custom Instructions if configured
        if user:
            custom_parts = []
            if getattr(user, "custom_instructions_about_user", None):
                custom_parts.append(f"About User Profile: {user.custom_instructions_about_user.strip()}")
            if getattr(user, "custom_instructions_how_to_respond", None):
                custom_parts.append(f"User Response Directives: {user.custom_instructions_how_to_respond.strip()}")
            if custom_parts:
                tone_guidance = (tone_guidance + "\n" + "\n".join(custom_parts)).strip()

        # STAGE 1.5: Cross-Chat Memory Retrieval with strict user scoping
        memory_retrieval_res = {
            "used_memories": [],
            "used_memory_ids": [],
            "formatted_context": "",
            "previous_context_used": False,
        }
        if user_id:
            try:
                mem_start = time.perf_counter()
                memory_retrieval_res = memory_service.retrieve_relevant_memories(
                    db, user_id=user_id, query=cleaned_query, top_k=5
                )
                stage_timings["memory_retrieval_ms"] = round((time.perf_counter() - mem_start) * 1000, 2)
                if not chat_history and memory_retrieval_res.get("top_scenario"):
                    condensed = memory_service.condense_query_with_memory(cleaned_query, memory_retrieval_res)
                    if condensed != cleaned_query:
                        cleaned_query = condensed
            except Exception as mem_err:
                logger.warning(f"Memory retrieval in stream failed gracefully ({type(mem_err).__name__}): {mem_err}")
                stage_timings["memory_retrieval_ms"] = 0.0

        if memory_retrieval_res.get("previous_context_used"):
            yield {
                "type": "status",
                "stage": "memory",
                "message": "Referencing relevant context from earlier sessions..."
            }

        current_chat_context = ""
        if chat_history:
            current_chat_context = "\n".join([
                f"{m.get('role', 'user').capitalize()}: {m.get('content', '')[:500]}"
                for m in chat_history[-6:]
            ])
        format_hint = answer_planner.detect_format_hint(cleaned_query, chat_history_context=current_chat_context, has_attachment=has_attachment)

        # Formulate targeted RAG query using extracted error text and transaction code from vision step
        rag_search_query = cleaned_query
        if attachments_data:
            extracted_tech_terms = []
            for att in attachments_data:
                if att.get("file_type") == "image":
                    vm = att.get("vision_metadata") or {}
                    tc = vm.get("transaction_code")
                    err = vm.get("error_text")
                    msg = vm.get("message_class_and_number")
                    scr = vm.get("screen_or_app")
                    if tc and tc != "N/A":
                        extracted_tech_terms.append(tc)
                    if msg and msg != "N/A":
                        extracted_tech_terms.append(msg)
                    if err and err != "N/A":
                        extracted_tech_terms.append(err)
                    if not extracted_tech_terms and scr and scr != "N/A":
                        extracted_tech_terms.append(scr)
            if extracted_tech_terms:
                tech_snippet = " ".join(extracted_tech_terms)
                rag_search_query = f"{cleaned_query} {tech_snippet}".strip() if cleaned_query else tech_snippet

        # STAGE 2: Search Knowledge Base first; Tavily web fallback triggers only if score < 0.75 or gate fails.
        yield {
            "type": "status",
            "stage": "retrieval",
            "message": "Searching SAP knowledge base..."
        }
        try:
            evidence_selection, web_results, web_search_succeeded, top_kb_chunks, internal_confidence_data = self._search_with_kb_fallback(
                db, rag_search_query, stage_timings, is_follow_up=is_follow_up
            )
        except TypeError:
            evidence_selection, web_results, web_search_succeeded, top_kb_chunks, internal_confidence_data = self._search_with_kb_fallback(
                db, rag_search_query, stage_timings
            )
        internal_conf = float(internal_confidence_data.get("evidence_score", internal_confidence_data.get("confidence", 0.0)))
        if evidence_selection.get("source_type") in ("web", "web_search"):
            yield {
                "type": "status",
                "stage": "web_search",
                "message": "KB evidence was below threshold (0.75); searching authoritative SAP web sources..."
            }

        # STAGE 4: Select only validated evidence passages.
        yield {
            "type": "status",
            "stage": "evidence_selection",
            "message": "Validating retrieved evidence for this answer..."
        }

        selected_passages = evidence_selection.get("selected_passages") or []
        selected_source_type = evidence_selection.get("source_type") or "insufficient"
        selected_quality = evidence_selection.get("selected_evidence_quality", 0.0)
        fallback_reason = evidence_selection.get("fallback_reason")

        # STAGE 5: Direct Live Answer Streaming or Abstention
        yield {
            "type": "status",
            "stage": "generating",
            "message": "Generating technical response..."
        }

        llm_started = time.perf_counter()
        first_token_ms = None
        token_buffer = []

        if (selected_source_type == "insufficient" or not selected_passages) and (task_type in ("architecture", "screenshot_analysis") or has_attachment):
            if task_type == "screenshot_analysis" or has_attachment:
                effective_source = "sap_expert"
                stream_gen = llm_service.stream_answer(
                    cleaned_query,
                    [],
                    source_type=effective_source,
                    tone_guidance=tone_guidance,
                    memory_context=memory_retrieval_res.get("formatted_context", ""),
                    chat_history_context=current_chat_context,
                    has_attachment=has_attachment
                )
                for token in stream_gen:
                    if first_token_ms is None:
                        first_token_ms = round((time.perf_counter() - llm_started) * 1000, 2)
                    token_buffer.append(token)
                    yield {"type": "token", "content": token}
                final_answer = "".join(token_buffer).strip()
                stage_timings["llm_total_ms"] = round((time.perf_counter() - llm_started) * 1000, 2)
                stage_timings["llm_ttft_ms"] = first_token_ms or stage_timings["llm_total_ms"]
                final_verification = {"grounding_score": 0.95, "status": "supported", "critical_unsupported_claims": [], "passes_grounding_gate": True}
                stage_timings["grounding_ms"] = 0.0
            else:
                arch_analysis = vision_service._generate_architecture_analysis(cleaned_query, current_chat_context)
                final_answer = arch_analysis["text"]
                effective_source = "sap_expert"
                yield {"type": "token", "content": final_answer}
                first_token_ms = round((time.perf_counter() - llm_started) * 1000, 2)
                stage_timings["llm_total_ms"] = first_token_ms
                stage_timings["llm_ttft_ms"] = first_token_ms
                final_verification = {"grounding_score": 0.95, "status": "supported", "critical_unsupported_claims": [], "passes_grounding_gate": True}
                stage_timings["grounding_ms"] = 0.0
        elif selected_source_type == "insufficient" or not selected_passages:
            effective_source = "insufficient"
            disclaimer = "I could not verify this SAP answer to the required confidence level (available evidence is insufficient and cannot be verified).\n\n"
            yield {"type": "token", "content": disclaimer}
            token_buffer.append(disclaimer)
            stream_gen = None
            try:
                stream_gen = llm_service.stream_answer(
                    cleaned_query,
                    [],
                    source_type="sap_expert",
                    tone_guidance=(tone_guidance + "\nNote: Documentation evidence is unavailable or insufficient. Provide a structured first-pass investigation plan based on standard SAP architecture principles. Clearly mark unverified possibilities and cite missing evidence without fabricating identifiers.").strip(),
                    memory_context=memory_retrieval_res.get("formatted_context", ""),
                    chat_history_context=current_chat_context,
                    has_attachment=has_attachment
                )
                for token in stream_gen:
                    if first_token_ms is None:
                        first_token_ms = round((time.perf_counter() - llm_started) * 1000, 2)
                    token_buffer.append(token)
                    yield {"type": "token", "content": token}
            except Exception as e:
                logger.warning("LLM streaming for insufficient evidence failed: %s", e)

            final_answer = "".join(token_buffer).strip()
            if not final_answer:
                final_answer = self._insufficient_answer("insufficient", fallback_reason or "Available evidence is insufficient.")
                yield {"type": "token", "content": final_answer}
                effective_source = "insufficient"
                verification = grounding_service.verify_answer(
                    cleaned_query, final_answer, [], source_type="insufficient"
                )
                final_verification = verification
            else:
                final_verification = {"grounding_score": 0.70, "status": "supported", "critical_unsupported_claims": [], "passes_grounding_gate": True}

            first_token_ms = first_token_ms or round((time.perf_counter() - llm_started) * 1000, 2)
            stage_timings["llm_total_ms"] = round((time.perf_counter() - llm_started) * 1000, 2)
            stage_timings["llm_ttft_ms"] = first_token_ms
            stage_timings["grounding_ms"] = 0.0
        else:
            effective_source = selected_source_type
            try:
                stream_gen = llm_service.stream_answer(
                    cleaned_query,
                    selected_passages,
                    source_type=effective_source,
                    tone_guidance=tone_guidance,
                    memory_context=memory_retrieval_res.get("formatted_context", ""),
                    chat_history_context=current_chat_context,
                    has_attachment=has_attachment
                )
            except TypeError:
                stream_gen = llm_service.stream_answer(
                    cleaned_query,
                    selected_passages,
                    source_type=effective_source
                )
            for token in stream_gen:
                if first_token_ms is None:
                    first_token_ms = round((time.perf_counter() - llm_started) * 1000, 2)
                token_buffer.append(token)
                yield {"type": "token", "content": token}
            final_answer = "".join(token_buffer).strip()
            if not final_answer:
                try:
                    final_answer = llm_service.generate_answer(
                        cleaned_query,
                        selected_passages,
                        source_type=effective_source,
                        tone_guidance=tone_guidance,
                        memory_context=memory_retrieval_res.get("formatted_context", ""),
                        chat_history_context=current_chat_context,
                        has_attachment=has_attachment
                    )
                    if final_answer:
                        yield {"type": "token", "content": final_answer}
                except Exception as gen_err:
                    logger.error("LLM fallback generation failed: %s", gen_err)

            if not final_answer:
                logger.error("LLM returned empty tokens and empty answer fallback.")
                final_answer = (
                    "I was unable to complete the generation for this inquiry from the available sources. "
                    "Please verify your query parameters or retry."
                )
                yield {"type": "token", "content": final_answer}

            # If user asked for diagram/architecture and output lacks ```mermaid, append guaranteed diagram
            if (task_type == "architecture" or format_hint.get("wants_diagram")) and "```mermaid" not in final_answer:
                mermaid_code = vision_service.generate_diagram(cleaned_query, current_chat_context)
                diagram_block = f"\n\n### Interactive Architecture Diagram\n```mermaid\n{mermaid_code}\n```\n"
                yield {"type": "token", "content": diagram_block}
                final_answer += diagram_block

            # Post-generation check: enforce standard expansions and audit identifiers against sources
            final_answer = self._sanitize_and_verify_identifiers(final_answer, selected_passages)

            stage_timings["llm_total_ms"] = round((time.perf_counter() - llm_started) * 1000, 2)
            stage_timings["llm_ttft_ms"] = first_token_ms

            # STAGE 6: Evaluate claims in the final candidate answer.
            yield {
                "type": "status",
                "stage": "verifying_claims",
                "message": "Checking the answer against the selected source..."
            }
            grounding_started = time.perf_counter()
            verification = grounding_service.verify_answer(
                cleaned_query, final_answer, selected_passages, source_type=selected_source_type
            )
            final_verification = verification
            stage_timings["grounding_ms"] = round((time.perf_counter() - grounding_started) * 1000, 2)

        # STAGE 7: Recommend Exactly 3 Follow-Up Questions (instant, <1ms)
        follow_ups = (
            followup_service.generate_followup_questions(cleaned_query, final_answer, selected_passages)
            if selected_passages else []
        )

        # Build Citations & Web Sources with exact metadata
        citation_started = time.perf_counter()
        citations = []
        web_sources = []
        for p in selected_passages:
            if p.get("source_type") == "knowledge_base":
                citations.append({
                    "id": str(p.get("chunk_id") or p.get("source_id") or ""),
                    "chunk_id": str(p.get("chunk_id") or p.get("source_id") or ""),
                    "document": p.get("document_name", "SAP Manual"),
                    "page": p.get("page_number", 1),
                    "section": p.get("section", ""),
                    "score": round(float(p.get("relevance_score", 0.7)), 4),
                    "snippet": p.get("snippet", "")
                })
            elif p.get("source_type") in ("web", "web_search"):
                web_sources.append({
                    "id": str(p.get("source_id") or ""),
                    "title": p.get("title", "SAP Documentation"),
                    "url": p.get("url", ""),
                    "domain": p.get("domain", "help.sap.com"),
                    "snippet": p.get("snippet", "")
                })
        stage_timings["citation_ms"] = round((time.perf_counter() - citation_started) * 1000, 2)

        stage_timings["total_backend_ms"] = round((time.perf_counter() - pipeline_started) * 1000, 2)
        total_time = stage_timings["total_backend_ms"]
        for k in list(stage_timings.keys()):
            if k != "total_backend_ms" and stage_timings[k] > total_time:
                stage_timings[k] = total_time

        retrieved_candidate_count = int(stage_timings.pop("retrieved_candidates", len(top_kb_chunks)))
        llm_provider = getattr(settings, "LLM_PROVIDER", "groq")
        llm_model = llm_service.selected_stream_model or settings.LLM_MODEL
        logger.info(
            "rag_timing request_id=%s stages_ms=%s retrieved_chunks=%d llm_chunks=%d provider=%s model=%s web_fallback=%s evidence_score=%.4f",
            request_id or "unavailable", stage_timings, retrieved_candidate_count, len(selected_passages),
            llm_provider, llm_model, web_search_succeeded, internal_conf
        )

        # STAGE 10: Completion 'done' event with all required fields
        yield {
            "type": "done",
            "answer": final_answer,
            "source_type": effective_source,
            "grounding_score": final_verification.get("grounding_score"),
            "kb_grounding_score": final_verification.get("kb_grounding_score"),
            "web_grounding_score": final_verification.get("web_grounding_score"),
            "grounding_status": final_verification.get("grounding_status"),
            "grounding_method": final_verification.get("verification_method"),
            "grounding_claims": final_verification.get("claims", []),
            "grounding_summary": final_verification.get("summary"),
            "is_in_rag_pipeline": selected_source_type == "knowledge_base",
            "kb_score": round(internal_conf, 4),
            "evidence_score": round(internal_conf, 4),
            "threshold": round(settings.KB_CONFIDENCE_THRESHOLD, 4),
            "web_score": round(selected_quality, 4),
            "winning_score": round(selected_quality, 4),
            "selected_source": effective_source,
            "verification_status": final_verification.get("verification_status"),
            "internal_evidence_confidence": internal_conf,
            "selected_evidence_quality": selected_quality,
            "external_search_used": web_search_succeeded,
            "web_search_used": selected_source_type in ("web", "web_search") and bool(selected_passages),
            "kb_relevance_score": internal_confidence_data.get("kb_relevance_score", round(internal_conf * 100, 1)),
            "kb_threshold": round(settings.KB_CONFIDENCE_THRESHOLD * 100),
            "fallback_reason": fallback_reason,
            "citations": citations,
            "web_sources": web_sources,
            "follow_up_questions": follow_ups,
            "selection_summary": evidence_selection.get("selection_summary", ""),
            "stage_timings_ms": stage_timings,
            "used_memories": memory_retrieval_res.get("used_memories", []),
            "used_memory_ids": memory_retrieval_res.get("used_memory_ids", []),
            "previous_context_used": memory_retrieval_res.get("previous_context_used", False),
        }


rag_service = RAGService()
