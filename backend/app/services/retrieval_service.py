import re
import time
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, desc

from backend.app.config import settings
from backend.app.models.chunk import DocumentChunk
from backend.app.services.embedding_service import embedding_service

from backend.app.services.evidence_selection_service import (
    STOP_WORDS,
    SCENARIO_META_STOP_WORDS,
    BRIM_SYNONYM_CLUSTERS,
)

class RetrievalService:
    @staticmethod
    def preprocess_query(query: str) -> str:
        # Normalize whitespace, keep relevant punctuation like hyphens and slashes (e.g. S/4HANA, T-Code)
        cleaned = re.sub(r"[ \t]+", " ", query).strip()
        return cleaned

    @staticmethod
    def _compute_keyword_score(query: str, text: str) -> float:
        """Computes BM25-inspired term frequency match with SAP acronym boosting and BRIM synonym support."""
        text_lower = text.lower()
        raw_tokens = re.findall(r"\b[a-z0-9\/\-_]+\b", query.lower())
        tokens = [
            t for t in raw_tokens
            if t not in STOP_WORDS
            and t not in SCENARIO_META_STOP_WORDS
            and not t.isdigit()
            and len(t) > 1
        ]
        if not tokens:
            tokens = [t for t in raw_tokens if t not in STOP_WORDS and len(t) > 1]
        if not tokens:
            return 0.0

        matches = 0
        boosted_matches = 0
        for token in tokens:
            count = text_lower.count(token)
            if count == 0:
                syns = BRIM_SYNONYM_CLUSTERS.get(token, set())
                for syn in syns:
                    c = text_lower.count(syn)
                    if c > 0:
                        count = c
                        break
            if count > 0:
                matches += 1
                # Boost SAP codes / tables / tcodes / modules
                if len(token) >= 4 or token in {"fi", "co", "mm", "sd", "pp", "qm", "pm", "hr", "ci", "cc", "som"}:
                    boosted_matches += min(count, 3)

        coverage = matches / len(tokens)
        density = min(boosted_matches / 6.0, 1.0)
        return float(0.7 * coverage + 0.3 * density)

    def __init__(self):
        self._cache_chunks: Optional[List[Dict[str, Any]]] = None
        self._cache_matrix: Optional[np.ndarray] = None
        self._cache_count: int = -1

    def invalidate_cache(self):
        self._cache_chunks = None
        self._cache_matrix = None
        self._cache_count = -1

    def warm_up(self, db: Session) -> int:
        """Materialize the local retrieval matrix before the first user query."""
        chunks, _ = self._get_cache(db)
        return len(chunks)

    def _get_cache(self, db: Session):
        current_count = db.query(DocumentChunk).count()
        if self._cache_chunks is not None and self._cache_count == current_count:
            return self._cache_chunks, self._cache_matrix

        all_chunks = db.query(DocumentChunk).all()
        chunks_meta = []
        vecs = []
        dim = settings.EMBEDDING_DIM
        for c in all_chunks:
            emb = c.embedding
            if emb and len(emb) == dim:
                v = np.array(emb, dtype=np.float32)
                norm = float(np.linalg.norm(v))
                if norm > 0:
                    v = v / norm
                else:
                    v = np.zeros(dim, dtype=np.float32)
            else:
                v = np.zeros(dim, dtype=np.float32)
            vecs.append(v)
            chunks_meta.append({
                "chunk_id": c.id,
                "document_id": c.document_id,
                "document_name": c.document_name,
                "page_number": c.page_number,
                "section": c.section or f"Page {c.page_number}",
                "chunk_text": c.chunk_text,
            })

        self._cache_chunks = chunks_meta
        self._cache_matrix = np.array(vecs, dtype=np.float32) if vecs else np.zeros((0, dim), dtype=np.float32)
        self._cache_count = current_count
        return self._cache_chunks, self._cache_matrix

    def hybrid_search(
        self,
        db: Session,
        query: str,
        top_k: Optional[int] = None,
        document_filter: Optional[str] = None,
        stage_timings: Optional[Dict[str, float]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Hybrid retrieval using vector similarity and lexical matching across all indexed documents."""
        k = top_k or settings.TOP_K
        processed_query = self.preprocess_query(query)

        embedding_started = time.perf_counter()
        query_vector_list = embedding_service.embed_text(processed_query)
        if stage_timings is not None:
            stage_timings["embedding_generation_ms"] = stage_timings.get("embedding_generation_ms", 0.0) + (time.perf_counter() - embedding_started) * 1000
        query_vector = np.array(query_vector_list, dtype=np.float32)
        q_norm = float(np.linalg.norm(query_vector))
        if q_norm > 0:
            query_vector = query_vector / q_norm

        dialect_name = getattr(getattr(db, "bind", None), "dialect", None)
        dialect_str = getattr(dialect_name, "name", "")
        retrieval_started = time.perf_counter()

        # 1️⃣ If running on PostgreSQL with pgvector, attempt accelerated DB-side query
        if dialect_str == "postgresql":
            try:
                database_query_started = time.perf_counter()
                vec_q = db.query(DocumentChunk)
                if document_filter:
                    vec_q = vec_q.filter(DocumentChunk.document_name == document_filter)

                vec_hits = (
                    vec_q.order_by(DocumentChunk.embedding.op("<=>")(query_vector_list))
                    .limit(k * 2)
                    .all()
                )

                lex_tokens = [
                    t for t in re.findall(r"\b[a-zA-Z0-9\/\-_]+\b", processed_query)
                    if t.lower() not in STOP_WORDS
                    and t.lower() not in SCENARIO_META_STOP_WORDS
                    and not t.isdigit()
                    and len(t) > 1
                ]
                lex_query_str = " ".join(lex_tokens) if lex_tokens else processed_query

                lex_q = db.query(
                    DocumentChunk,
                    func.ts_rank_cd(
                        func.to_tsvector("english", DocumentChunk.chunk_text),
                        func.plainto_tsquery("english", lex_query_str)
                    ).label("lex_score")
                )
                if document_filter:
                    lex_q = lex_q.filter(DocumentChunk.document_name == document_filter)

                lex_hits = (
                    lex_q.filter(func.to_tsvector("english", DocumentChunk.chunk_text).op("@@")(func.plainto_tsquery("english", lex_query_str)))
                    .order_by(desc("lex_score"))
                    .limit(k * 2)
                    .all()
                )

                if stage_timings is not None:
                    stage_timings["vector_database_retrieval_ms"] = stage_timings.get("vector_database_retrieval_ms", 0.0) + (time.perf_counter() - database_query_started) * 1000
                selection_started = time.perf_counter()

                denom = 60
                rrf_scores: Dict[str, float] = {}
                for rank, chunk in enumerate(vec_hits, start=1):
                    rrf_scores[chunk.id] = rrf_scores.get(chunk.id, 0.0) + 1.0 / (denom + rank)
                for rank, (chunk, _) in enumerate(lex_hits, start=1):
                    rrf_scores[chunk.id] = rrf_scores.get(chunk.id, 0.0) + 1.0 / (denom + rank)

                top_chunk_pairs = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:k]
                id_to_chunk = {c.id: c for c in vec_hits}
                id_to_chunk.update({c.id: c for c, _ in lex_hits})

                results: List[Dict[str, Any]] = []
                for chunk_id, _ in top_chunk_pairs:
                    chunk = id_to_chunk[chunk_id]
                    raw_emb = chunk.embedding
                    if raw_emb is not None and q_norm > 0:
                        c_vec = np.array(raw_emb, dtype=np.float32)
                        c_norm = float(np.linalg.norm(c_vec))
                        vec_sim = float(np.dot(query_vector, c_vec) / c_norm) if c_norm > 0 else 0.0
                    else:
                        vec_sim = 0.0
                    norm_vec = max(0.0, min(1.0, (vec_sim + 1.0) / 2.0))
                    kw_score = self._compute_keyword_score(processed_query, chunk.chunk_text)
                    hybrid_score = round(0.60 * norm_vec + 0.40 * kw_score, 4)

                    results.append({
                        "chunk_id": chunk.id,
                        "document_id": chunk.document_id,
                        "document_name": chunk.document_name,
                        "page_number": chunk.page_number,
                        "section": chunk.section or f"Page {chunk.page_number}",
                        "chunk_text": chunk.chunk_text,
                        "vector_score": round(norm_vec, 4),
                        "keyword_score": round(kw_score, 4),
                        "score": hybrid_score,
                    })

                if results:
                    if stage_timings is not None:
                        stage_timings["metadata_filter_selection_ms"] = stage_timings.get("metadata_filter_selection_ms", 0.0) + (time.perf_counter() - selection_started) * 1000
                    return results
            except Exception:
                pass  # Fall through to universal in-memory retrieval

        # 2️⃣ Accelerated In-Memory Vector Matrix Multiplication + Lexical Hybrid Search with RRF Fusion
        cached_meta, cached_matrix = self._get_cache(db)
        if not cached_meta or cached_matrix.shape[0] == 0:
            if stage_timings is not None:
                stage_timings["vector_database_retrieval_ms"] = stage_timings.get("vector_database_retrieval_ms", 0.0) + (time.perf_counter() - retrieval_started) * 1000
            return []

        # Vector dot products in a single matrix multiplication
        sims = cached_matrix @ query_vector  # shape (N,)
        normalized_sims = np.clip((sims + 1.0) / 2.0, 0.0, 1.0)

        # 1. Top dense vector candidates (top 250)
        top_vec_indices = np.argsort(-normalized_sims)[:min(250, len(cached_meta))]
        vec_rank_map: Dict[int, int] = {idx: rank for rank, idx in enumerate(top_vec_indices, start=1)}

        # 2. Lexical scoring across candidate chunks + top vector chunks
        selection_started = time.perf_counter()
        # Compute keyword score across candidates
        kw_scores: List[Tuple[int, float]] = []
        for idx in range(len(cached_meta)):
            # Fast filter: score chunks with vector relevance or containing query terms
            if idx in vec_rank_map or normalized_sims[idx] >= 0.35:
                meta = cached_meta[idx]
                if document_filter and meta["document_name"] != document_filter:
                    continue
                k_score = self._compute_keyword_score(processed_query, meta["chunk_text"])
                if k_score > 0.0:
                    kw_scores.append((idx, k_score))

        kw_scores.sort(key=lambda x: x[1], reverse=True)
        top_lex_candidates = kw_scores[:min(250, len(kw_scores))]
        lex_rank_map: Dict[int, int] = {item[0]: rank for rank, item in enumerate(top_lex_candidates, start=1)}

        # 3. Reciprocal Rank Fusion (RRF) combining dense and lexical ranks
        denom = 60
        all_candidate_indices = set(vec_rank_map.keys()) | set(lex_rank_map.keys())
        scored_candidates: List[Dict[str, Any]] = []

        seen_snippets = set()
        for idx in all_candidate_indices:
            meta = cached_meta[idx]
            if document_filter and meta["document_name"] != document_filter:
                continue

            v_score = float(normalized_sims[idx])
            k_score = next((s for i, s in kw_scores if i == idx), self._compute_keyword_score(processed_query, meta["chunk_text"]))

            # RRF calculation
            r_vec = vec_rank_map.get(idx, 999)
            r_lex = lex_rank_map.get(idx, 999)
            rrf_raw = (1.0 / (denom + r_vec)) + (1.0 / (denom + r_lex))

            # Calibrated composite hybrid score: 50% RRF signal + 30% vector + 20% keyword
            max_rrf = (1.0 / (denom + 1)) * 2
            normalized_rrf = min(1.0, rrf_raw / max_rrf)
            hybrid_score = round(0.40 * normalized_rrf + 0.35 * v_score + 0.25 * k_score, 4)

            # Deduplication: suppress near-identical text from same document
            text_snippet = meta["chunk_text"][:120].strip().lower()
            dedup_key = f"{meta['document_name']}::{text_snippet}"
            if dedup_key in seen_snippets:
                continue
            seen_snippets.add(dedup_key)

            scored_candidates.append({
                "chunk_id": meta["chunk_id"],
                "document_id": meta["document_id"],
                "document_name": meta["document_name"],
                "page_number": meta["page_number"],
                "section": meta["section"],
                "chunk_text": meta["chunk_text"],
                "vector_score": round(v_score, 4),
                "keyword_score": round(k_score, 4),
                "rrf_score": round(normalized_rrf, 4),
                "score": hybrid_score,
            })

        scored_candidates.sort(key=lambda x: x["score"], reverse=True)
        if stage_timings is not None:
            stage_timings["vector_database_retrieval_ms"] = stage_timings.get("vector_database_retrieval_ms", 0.0) + (time.perf_counter() - retrieval_started) * 1000
            stage_timings["metadata_filter_selection_ms"] = stage_timings.get("metadata_filter_selection_ms", 0.0) + (time.perf_counter() - selection_started) * 1000
        return scored_candidates[:k]

retrieval_service = RetrievalService()

