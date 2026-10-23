import re
from typing import List, Dict, Any, Tuple
from backend.app.config import settings

STOP_WORDS = {
    "what", "is", "the", "a", "an", "how", "to", "in", "of", "and", "for", "with",
    "does", "do", "explain", "describe", "can", "you", "tell", "me", "about", "which",
    "are", "why", "where", "when", "by", "from", "on", "at", "as", "into"
}

SAP_DISTINCT_PRODUCTS = {
    "ariba", "concur", "fieldglass", "hybris", "c4c", "qualtrics", "celonis",
    "successfactors", "btp", "signavio", "leanix", "walkme"
}


class RerankingService:
    @staticmethod
    def _extract_query_tokens(query: str) -> List[str]:
        raw_tokens = re.findall(r"\b[a-z0-9\/\-_]+\b", query.lower())
        return [t for t in raw_tokens if t not in STOP_WORDS and len(t) > 1]

    def rerank_kb(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_n: int = None,
        threshold: float = None
    ) -> Tuple[List[Dict[str, Any]], float, bool]:
        """
        Reranks knowledge base candidate chunks using multi-factor scoring:
        - Vector similarity & BM25 keyword score
        - Section/heading match bonus
        - Multi-word exact n-gram phrase match
        - Entity presence validation (e.g. for distinct cloud products)
        Returns: (top_chunks, top_kb_score, has_sufficient_evidence)
        """
        if not candidates:
            return [], 0.0, False

        n = top_n or settings.RERANK_TOP_K
        thresh = settings.INTERNAL_EVIDENCE_THRESHOLD if threshold is None else threshold
        query_lower = query.lower()
        query_tokens = self._extract_query_tokens(query)

        scored_candidates = []
        for c in candidates:
            base_score = float(c.get("score", 0.0))
            text_lower = (c.get("chunk_text") or "").lower()
            section_lower = (c.get("section") or "").lower()

            # 1. Section / Title match boost
            section_matches = sum(1 for w in query_tokens if w in section_lower and len(w) > 2)
            section_boost = min(section_matches * 0.05, 0.15)

            # 2. Multi-word exact n-gram boost
            ngram_boost = 0.0
            words_list = query_lower.split()
            if len(words_list) >= 2:
                for i in range(len(words_list) - 1):
                    bigram = f"{words_list[i]} {words_list[i+1]}"
                    if bigram in text_lower and len(bigram) > 6:
                        ngram_boost += 0.04
            ngram_boost = min(ngram_boost, 0.12)

            # 3. SAP technical identifiers / T-Code match boost
            id_boost = 0.0
            for token in query_tokens:
                if re.match(r"^[a-z]{1,2}\d{2}[a-z0-9]?$", token):  # e.g. me21n, fb01, migo
                    if token in text_lower:
                        id_boost += 0.06
            id_boost = min(id_boost, 0.10)

            rerank_score = min(base_score + section_boost + ngram_boost + id_boost, 1.0)
            c_copy = dict(c)
            c_copy["rerank_score"] = round(rerank_score, 4)
            scored_candidates.append(c_copy)

        scored_candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
        top_chunks = scored_candidates[:n]

        if not top_chunks:
            return [], 0.0, False

        top_score = top_chunks[0]["rerank_score"]

        # Entity presence validation:
        # If user is asking about specific distinctive entities (e.g. Ariba, Concur),
        # verify that the chunk text actually contains that entity
        combined_text = " ".join([c["chunk_text"].lower() for c in top_chunks])
        for word in query_tokens:
            if word in SAP_DISTINCT_PRODUCTS and word not in combined_text:
                return top_chunks, top_score, False

        has_sufficient = (top_score >= thresh)
        return top_chunks, top_score, has_sufficient

    def rerank_web(
        self,
        query: str,
        web_results: List[Dict[str, Any]],
        top_n: int = 3
    ) -> Tuple[List[Dict[str, Any]], float]:
        """
        Reranks and scores authoritative SAP web search results:
        - Query term coverage in title and snippet
        - Exact query phrase presence
        - Official SAP domain authority (help.sap.com > community.sap.com > generic)
        Returns: (top_web_results, top_web_score)
        """
        if not web_results:
            return [], 0.0

        query_lower = query.lower()
        query_tokens = self._extract_query_tokens(query)
        scored_web = []

        for item in web_results:
            title = (item.get("title") or "").lower()
            snippet = (item.get("snippet") or "").lower()
            extracted = (item.get("chunk_text") or item.get("content") or "").lower()
            domain = (item.get("domain") or "").lower()
            combined = f"{title} {snippet} {extracted}"

            # 1. Query token coverage
            matched_tokens = sum(1 for t in query_tokens if t in combined)
            coverage = (matched_tokens / len(query_tokens)) if query_tokens else 0.5

            # 2. Title relevance
            title_matches = sum(1 for t in query_tokens if t in title)
            title_boost = min(title_matches * 0.08, 0.20)

            # 3. Exact query phrase match in snippet or title
            phrase_boost = 0.0
            if len(query_tokens) >= 2:
                for i in range(len(query_tokens) - 1):
                    pair = f"{query_tokens[i]} {query_tokens[i+1]}"
                    if pair in combined:
                        phrase_boost += 0.06
            phrase_boost = min(phrase_boost, 0.15)

            # 4. Domain authority weighting
            domain_weight = (
                0.05 if any(host in domain for host in ("help.sap.com", "learning.sap.com"))
                else (0.03 if any(host in domain for host in ("community.sap.com", "blogs.sap.com")) else 0.0)
            )

            # 5. Composite web relevance score (calibrated 0.0 to 1.0)
            raw_score = 0.55 * coverage + title_boost + phrase_boost + domain_weight
            configured_priority = item.get("source_priority")
            if configured_priority in (1, 2, 3):
                # Small tie-breaker for the user's curated SAP pages; query
                # relevance remains the main ranking signal.
                raw_score += (4 - configured_priority) * 0.015
            final_web_score = max(0.0, min(1.0, round(raw_score, 4)))

            w_copy = dict(item)
            w_copy["score"] = final_web_score
            w_copy["rerank_score"] = final_web_score
            w_copy["vector_score"] = round(min(1.0, coverage + 0.1), 4)
            w_copy["keyword_score"] = round(coverage, 4)
            # Preserve extracted page text for answer generation and grounding.
            w_copy["chunk_text"] = (
                item.get("chunk_text") or f"{item.get('title', '')}: {item.get('snippet', '')}"
            )
            scored_web.append(w_copy)

        scored_web.sort(key=lambda x: x["rerank_score"], reverse=True)
        top_web = scored_web[:top_n]
        top_score = top_web[0]["rerank_score"] if top_web else 0.0
        return top_web, top_score

    def compare_and_select(
        self,
        query: str,
        kb_candidates: List[Dict[str, Any]],
        web_results: List[Dict[str, Any]],
        threshold: float = None,
    ) -> Dict[str, Any]:
        """Legacy adapter that now delegates to the strict 75-point source router."""
        from backend.app.services.evidence_selection_service import EvidenceSelectionService

        router = EvidenceSelectionService()
        if threshold is not None:
            router.internal_threshold = threshold
        top_kb_chunks, _, _ = self.rerank_kb(
            query, kb_candidates, top_n=settings.RERANK_TOP_K,
            threshold=router.internal_threshold,
        )
        relevance = router.compute_internal_confidence(query, top_kb_chunks)
        selection = router.select_strongest_evidence(
            query, top_kb_chunks, web_results, relevance
        )
        winner = selection["source_type"]
        top_web_results, web_score = self.rerank_web(query, web_results, top_n=5)
        return {
            "winner": winner,
            "is_in_rag_pipeline": winner == "knowledge_base",
            "kb_score": round(float(relevance.get("confidence", 0.0)), 4),
            "kb_relevance_score": relevance.get("kb_relevance_score", 0.0),
            "kb_threshold": round(router.internal_threshold * 100),
            "web_score": round(web_score, 4),
            "winning_score": round(float(selection.get("selected_evidence_quality", 0.0)), 4),
            "evidence": selection.get("selected_passages", []),
            "top_kb_chunks": top_kb_chunks,
            "top_web_results": top_web_results,
            "reason": selection.get("selection_summary", ""),
            "fallback_reason": selection.get("fallback_reason"),
        }

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_n: int = None,
        threshold: float = None
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """Backwards-compatible API for legacy callers."""
        top_chunks, _, has_sufficient = self.rerank_kb(query, candidates, top_n, threshold)
        return top_chunks, has_sufficient


reranking_service = RerankingService()
