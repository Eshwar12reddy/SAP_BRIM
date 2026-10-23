from unittest.mock import Mock

from backend.app.services.evidence_selection_service import EvidenceSelectionService
from backend.app.services.llm_service import LLMService
from backend.app.services.query_rewriter import QueryRewriter


def test_web_selection_rejects_evidence_below_coverage_gate(monkeypatch):
    service = EvidenceSelectionService()
    passage = {
        "source_type": "web",
        "title": "SAP Help",
        "url": "https://help.sap.com/docs/brim",
        "domain": "help.sap.com",
        "snippet": "SAP BRIM billable items are handled in invoicing.",
        "chunk_text": "SAP BRIM billable items are handled in invoicing.",
        "authority_tier": 1,
        "score": 0.99,
    }
    monkeypatch.setattr(
        "backend.app.services.evidence_selection_service.reranking_service.rerank_web",
        lambda query, candidates, top_n=5: (candidates, 0.99),
    )

    result = service.select_strongest_evidence(
        "SAP BRIM billable items configuration workflow prerequisites recovery",
        [],
        [passage],
        {"confidence": 0.0},
    )

    assert result["source_type"] == "insufficient"
    assert result["selected_passages"] == []


def test_nonstream_generation_and_grounding_use_at_most_one_provider_fallback(monkeypatch):
    service = LLMService()
    service.groq_api_key = "configured"
    service.gemini_api_key = "AIza-configured"
    service.openrouter_api_key = "configured"
    attempted = []

    def fail(provider):
        def _call(*args, **kwargs):
            attempted.append(provider)
            return None
        return _call

    monkeypatch.setattr(service, "_call_groq", fail("groq"))
    monkeypatch.setattr(service, "_call_gemini", fail("gemini"))
    monkeypatch.setattr(service, "_call_openrouter", fail("openrouter"))
    monkeypatch.setattr(
        service,
        "_generate_grounded_local_response",
        lambda **kwargs: "Locally grounded response.",
    )
    passage = {
        "source_type": "web",
        "title": "SAP Help",
        "url": "https://help.sap.com/docs/brim",
        "domain": "help.sap.com",
        "snippet": "SAP BRIM billable items are handled in invoicing.",
        "chunk_text": "SAP BRIM billable items are handled in invoicing.",
    }

    assert service.generate_answer("SAP BRIM billable items", [passage]) == "Locally grounded response."
    assert attempted == ["groq", "gemini"]

    attempted.clear()
    assert service.generate_completion("Ground this claim.") == ""
    assert attempted == ["groq", "gemini"]


def test_provider_fallback_skips_unconfigured_tiers(monkeypatch):
    service = LLMService()
    service.groq_api_key = "configured"
    service.gemini_api_key = ""
    service.openrouter_api_key = "configured"
    attempted = []
    monkeypatch.setattr(service, "_call_groq", lambda *args, **kwargs: attempted.append("groq"))
    monkeypatch.setattr(service, "_call_gemini", lambda *args, **kwargs: attempted.append("gemini"))
    monkeypatch.setattr(service, "_call_openrouter", lambda *args, **kwargs: attempted.append("openrouter"))

    assert service.generate_completion("Ground this claim.") == ""
    assert attempted == ["groq", "openrouter"]


def test_streaming_uses_at_most_one_provider_fallback(monkeypatch):
    service = LLMService()
    service.groq_api_key = "configured"
    service.gemini_api_key = "AIza-configured"
    service.openrouter_api_key = "configured"
    attempted = []

    def no_tokens(provider):
        def _stream(*args, **kwargs):
            attempted.append(provider)
            return iter(())
        return _stream

    monkeypatch.setattr(service, "_stream_groq", no_tokens("groq"))
    monkeypatch.setattr(service, "_stream_gemini", no_tokens("gemini"))
    monkeypatch.setattr(service, "_stream_openrouter", no_tokens("openrouter"))
    monkeypatch.setattr(
        service,
        "_generate_grounded_local_response",
        lambda **kwargs: "Local grounded response.",
    )
    passage = {
        "source_type": "web",
        "title": "SAP Help",
        "url": "https://help.sap.com/docs/brim",
        "domain": "help.sap.com",
        "snippet": "SAP BRIM billable items are handled in invoicing.",
        "chunk_text": "SAP BRIM billable items are handled in invoicing.",
    }

    assert "".join(service.stream_answer("SAP BRIM billable items", [passage])) == "Local grounded response."
    assert attempted == ["groq", "gemini"]


def test_followup_rewrite_makes_only_one_remote_attempt():
    rewriter = QueryRewriter()
    create = Mock(side_effect=RuntimeError("provider unavailable"))
    rewriter.client = Mock()
    rewriter.client.chat.completions.create = create
    history = [
        {"role": "user", "content": "What is SAP Convergent Charging?"},
        {"role": "assistant", "content": "SAP CC rates usage events."},
    ]

    result = rewriter.resolve_query("What happens next?", history)

    assert create.call_count == 1
    assert result["resolved_query"]
    assert "Convergent Charging" in result["resolved_query"]
