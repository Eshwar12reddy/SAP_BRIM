import time
from unittest.mock import MagicMock, patch
import pytest

from backend.app.config import settings
from backend.app.services.web_search_service import (
    WebSearchService,
    TavilySearchError,
)
from backend.app.services.rag_service import RAGService


def test_tavily_query_cap_and_deduplication():
    rag = RAGService()
    # Query with repeated ideas and variations
    query = "SAP BRIM subscription cancellation billing run"
    queries = rag._generate_search_queries(query)
    
    assert len(queries) <= getattr(settings, "TAVILY_MAX_QUERIES", 2)
    assert len(queries) == len(set(queries))


def test_tavily_timeout_stops_promptly_and_bounded_retries():
    service = WebSearchService()
    call_count = 0

    class TimingOutClient:
        def search(self, **kwargs):
            nonlocal call_count
            call_count += 1
            raise TimeoutError("Connection to Tavily timed out")

    service.api_key = "test_key"
    service.client = TimingOutClient()

    with pytest.raises(TavilySearchError):
        service.search_sap_authoritative("SAP BRIM billing run", deadline=time.perf_counter() + 2.0)

    # Max retries is 1, so 1 initial attempt + 1 retry = 2 calls max
    assert call_count <= (1 + settings.TAVILY_MAX_RETRIES)


def test_tavily_overall_deadline_stops_searching():
    service = WebSearchService()
    call_count = 0

    class FakeClient:
        def search(self, **kwargs):
            nonlocal call_count
            call_count += 1
            # Simulate a search that took longer than deadline
            time.sleep(0.05)
            raise TimeoutError("Read timeout")

    service.api_key = "test_key"
    service.client = FakeClient()

    # Pass an already expired deadline
    deadline = time.perf_counter() - 0.1
    results = service.search_sap_authoritative("SAP BRIM billing run", deadline=deadline)
    # Should stop immediately without calling search
    assert results == []
    assert call_count == 0


def test_tavily_failure_falls_back_to_available_kb_evidence():
    rag = RAGService()
    kb_candidates = [{
        "chunk_id": "chunk-101",
        "title": "SAP BRIM Invoicing Guide",
        "url": "https://help.sap.com/docs/brim-invoicing",
        "chunk_text": "Invoicing processes billing documents and generates FI-CA open items.",
        "snippet": "Invoicing processes billing documents and generates FI-CA open items.",
        "score": 0.68,
        "source_type": "knowledge_base",
    }]

    # When web search fails
    with patch("backend.app.services.rag_service.web_search_service.search_sap_authoritative", side_effect=TavilySearchError("Timeout")):
        selection, web_results, web_success = rag._search_web_only(
            "SAP BRIM invoicing",
            internal_confidence_data={"confidence": 0.68, "term_coverage": 0.8},
            internal_candidates=kb_candidates,
        )
        
        # Must fall back to internal KB candidates rather than returning nothing
        selected = selection.get("selected_passages", [])
        assert len(selected) > 0
        assert selection.get("source_type") in ("knowledge_base", "sap_expert")
        assert selected[0]["chunk_id"] == "chunk-101"


def test_empty_llm_generation_not_treated_as_success():
    rag = RAGService()
    # Mock LLM to return empty string
    with patch("backend.app.services.rag_service.llm_service.generate_answer", return_value=""):
        with patch.object(rag, "_search_with_kb_fallback") as mock_eval:
            mock_eval.return_value = (
                {
                    "selected_passages": [{
                        "chunk_id": "c1",
                        "chunk_text": "Sample text",
                        "snippet": "Sample text",
                        "score": 0.8,
                        "source_type": "knowledge_base",
                        "title": "Doc",
                        "url": "https://help.sap.com",
                    }],
                    "source_type": "knowledge_base",
                    "evidence_score": 0.8,
                    "is_sufficient": True,
                    "needs_web_fallback": False,
                    "candidate_passages": [],
                },
                [],
                False,
                [],
                {"confidence": 0.8},
            )
            res = rag.process_query(MagicMock(), "How to configure BITs?")
            
            # Empty response must NEVER be returned as a blank success
            assert res["answer"] != ""
            assert len(res["answer"]) > 10
            # Either fallback structured response or evidence-limited note
            assert "SAP" in res["answer"] or "investigation" in res["answer"].lower() or "knowledge base" in res["answer"].lower()


def test_timing_instrumentation_stages_bounded_by_total():
    rag = RAGService()
    with patch("backend.app.services.rag_service.llm_service.generate_answer", return_value="SAP BRIM uses CI for invoicing."):
        with patch.object(rag, "_search_with_kb_fallback") as mock_eval:
            mock_eval.return_value = (
                {
                    "selected_passages": [{
                        "chunk_id": "c1",
                        "chunk_text": "CI handles invoicing.",
                        "snippet": "CI handles invoicing.",
                        "score": 0.85,
                        "source_type": "knowledge_base",
                        "title": "Doc",
                        "url": "https://help.sap.com",
                    }],
                    "source_type": "knowledge_base",
                    "evidence_score": 0.85,
                    "is_sufficient": True,
                    "needs_web_fallback": False,
                    "candidate_passages": [],
                },
                [],
                False,
                [],
                {"confidence": 0.85},
            )
            res = rag.process_query(MagicMock(), "What is CI in SAP BRIM?")
            timings = res.get("stage_timings_ms", {})
            total_ms = timings.get("total_backend_ms", 1.0)
            
            # Check individual stage bounds
            for stage, stage_ms in timings.items():
                if stage != "total_backend_ms" and isinstance(stage_ms, (int, float)):
                    assert stage_ms <= total_ms + 0.01, f"Stage {stage} ({stage_ms}ms) exceeded total ({total_ms}ms)"
            
            assert res["source_type"] == "knowledge_base"
            assert len(res["citations"]) > 0
