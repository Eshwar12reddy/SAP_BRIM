import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

@pytest.fixture
def auth_headers():
    client.post("/api/auth/register", json={"email": "rag_evaluator@sap.com", "name": "Evaluator", "password": "Password123!"})
    login_resp = client.post("/api/auth/login", json={"email": "rag_evaluator@sap.com", "password": "Password123!"}).json()
    return {"Authorization": f"Bearer {login_resp['access_token']}"}

def test_rag_answer_uses_web_sources_even_when_kb_has_matching_content(auth_headers):
    resp = client.post(
        "/api/rag/query",
        json={"query": "Explain the 3-Way Match verification process in SAP MM"},
        headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["source_type"] in ("web", "insufficient")
    assert data["citations"] == []
    assert data["is_in_rag_pipeline"] is False
    for source in data["web_sources"]:
        assert source["url"].startswith("https://")
        assert any(host in source["url"] for host in ("sap.com", "learning.sap.com"))

def test_rag_web_fallback_for_external_topics(auth_headers):
    # Query for SAP Ariba cloud procurement (not in our 10 primary on-prem manuals)
    resp = client.post(
        "/api/rag/query",
        json={"query": "How does SAP Ariba integrate with S/4HANA for supplier sourcing?"},
        headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["source_type"] in ["web", "insufficient"]
    assert data["citations"] == []
