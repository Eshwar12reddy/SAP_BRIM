from tavily import InvalidAPIKeyError

from backend.app.config import settings
from backend.app.services.web_search_service import (
    SAP_SOURCE_URLS,
    TavilyAuthenticationError,
    WebSearchService,
)


def test_approved_domain_matching_rejects_host_spoofing():
    from backend.app.services.web_search_service import web_search_service

    assert web_search_service._is_approved_sap_domain("https://help.sap.com/docs/brim") is True
    assert web_search_service._is_approved_sap_domain("https://evil-help.sap.com.evil.test/docs") is False


def test_tavily_fast_search_uses_preview_without_fetching_raw_pages():
    from backend.app.services.web_search_service import WebSearchService

    service = WebSearchService()
    class FakeTavily:
        def search(self, **kwargs):
            assert kwargs["include_raw_content"] is False
            assert kwargs["search_depth"] == "fast"
            assert kwargs["max_results"] <= 5
            assert kwargs["timeout"] <= max(8.0, float(settings.TAVILY_TIMEOUT_SECONDS))
            return {"results": [{
                "title": "SAP Help billable items",
                "url": "https://help.sap.com/docs/brim/billable-items",
                "content": "Short preview",
                "raw_content": "This should not be fetched or used.",
            }]}

    service.client = FakeTavily()
    result = service.search_sap_authoritative("SAP BRIM billable items")
    assert len(result) == 1
    assert "Short preview" in result[0]["chunk_text"]
    assert "should not be fetched" not in result[0]["chunk_text"]
    assert result[0]["snippet"] == "Short preview"


def test_non_sap_tavily_results_are_rejected_without_non_tavily_fallback():
    service = WebSearchService()

    class FakeTavily:
        def search(self, **kwargs):
            return {"results": [{
                "title": "Unapproved result",
                "url": "https://example.com/sap-brim",
                "content": "Not an SAP source",
            }]}

    service.client = FakeTavily()
    results = service.search_sap_authoritative("SAP BRIM")

    assert results == []


def test_non_https_sap_result_is_not_accepted():
    from backend.app.services.web_search_service import web_search_service

    assert web_search_service._is_approved_sap_domain("http://help.sap.com/docs/brim") is False


def test_curated_sap_brim_urls_have_priorities_and_match_child_pages():
    assert len(SAP_SOURCE_URLS) == 7
    assert WebSearchService._configured_source_priority(
        "https://help.sap.com/docs/BRIM/convergent-invoicing"
    ) == 1
    assert WebSearchService._configured_source_priority(
        "https://learning.sap.com/learning-journeys/sap-billing-and-revenue-innovation-management-brim-implementing-usage-to-cash"
    ) == 2
    assert WebSearchService._configured_source_priority(
        "https://community.sap.com/topics/billing-revenue-innovation-management"
    ) == 3


def test_missing_tavily_key_is_reported_for_kb_fallback(monkeypatch):
    monkeypatch.setattr(settings, "WEB_SEARCH_API_KEY", "")
    service = WebSearchService()

    try:
        service.search_sap_authoritative("SAP BRIM")
    except TavilyAuthenticationError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("missing Tavily key must be reported")


def test_invalid_tavily_key_is_reported_for_kb_fallback():
    service = WebSearchService()

    class FakeTavily:
        def search(self, **kwargs):
            raise InvalidAPIKeyError("invalid API key")

    service.api_key = "configured"
    service.client = FakeTavily()
    try:
        service.search_sap_authoritative("SAP BRIM")
    except TavilyAuthenticationError as exc:
        assert "invalid" in str(exc)
    else:
        raise AssertionError("invalid Tavily key must be reported")
