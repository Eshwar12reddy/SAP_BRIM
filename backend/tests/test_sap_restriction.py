import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.services.sap_classifier import SAP_SCOPE_REFUSAL, sap_classifier

client = TestClient(app)

def test_sap_classifier_acceptance():
    accepted_queries = [
        "What is SAP MM?",
        "Explain the SAP MM 3-way match in purchasing",
        "How do I create a purchase order with ME21N?",
        "What is the difference between table MARA and MARC?",
        "Explain Universal Journal table ACDOCA in S/4HANA",
        "How does F110 automatic payment program work in SAP FI?",
        "Describe SAP Fiori launchpad architecture",
        "What is the purpose of SAP Basis transaction SM50?",
        "What are Infotypes in SAP HCM?",
        "Explain CDS views and RAP in modern ABAP"
    ]
    for q in accepted_queries:
        is_sap, msg = sap_classifier.classify(q)
        assert is_sap is True, f"Query '{q}' should be accepted as SAP-related"

def test_sap_classifier_refusal():
    rejected_queries = [
        "What is Python?",
        "Write me a birthday message for my sister.",
        "What is cricket?",
        "Who is Elon Musk?",
        "Give me a chocolate cake recipe.",
        "How is the weather today?",
        "Tell me a joke about cats."
    ]
    for q in rejected_queries:
        is_sap, msg = sap_classifier.classify(q)
        assert is_sap is False, f"Query '{q}' should be rejected"
        assert msg == SAP_SCOPE_REFUSAL or "only help with sap" in msg.lower()


def test_contextual_sap_scenario_without_sap_keywords_is_accepted_only_with_sap_history():
    history = [
        {"role": "user", "content": "A SAP Convergent Invoicing billing run failed halfway through processing."},
        {"role": "assistant", "content": "The SAP CI run needs investigation."},
    ]
    contextual_question = "How should I investigate the failure and resume processing safely?"

    assert sap_classifier.classify(contextual_question)[0] is False
    assert sap_classifier.classify(contextual_question, chat_history=history)[0] is True


def test_unrelated_question_is_rejected_even_inside_sap_conversation():
    history = [{"role": "user", "content": "Explain SAP Convergent Invoicing."}]
    unrelated_questions = [
        "What is the capital of France?",
        "How is the weather today?",
        "Give me a chocolate cake recipe.",
    ]
    for question in unrelated_questions:
        assert sap_classifier.classify(question, chat_history=history)[0] is False

def test_rag_endpoint_refusal(monkeypatch):
    from backend.app.config import settings
    monkeypatch.setattr(settings, "GENERAL_QUESTIONS_ENABLED", False)

    # Register/login user
    client.post("/api/auth/register", json={"email": "tester_rag@sap.com", "name": "RAG Tester", "password": "Password123!"})
    login_resp = client.post("/api/auth/login", json={"email": "tester_rag@sap.com", "password": "Password123!"}).json()
    token = login_resp["access_token"]

    resp = client.post(
        "/api/rag/query",
        json={"query": "Write me a birthday poem."},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_type"] == "refusal"
    assert data["grounding_score"] is None
    assert data["answer"] == SAP_SCOPE_REFUSAL
    assert len(data["citations"]) == 0


def test_rag_endpoint_refuses_non_sap_even_when_general_knowledge_is_enabled(monkeypatch):
    from backend.app.config import settings
    monkeypatch.setattr(settings, "GENERAL_QUESTIONS_ENABLED", True)

    login_resp = client.post("/api/auth/login", json={"email": "tester_rag@sap.com", "password": "Password123!"}).json()
    token = login_resp["access_token"]

    resp = client.post(
        "/api/rag/query",
        json={"query": "How do electric cars work?"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_type"] == "refusal"
    assert data["answer"] == SAP_SCOPE_REFUSAL
    assert len(data["citations"]) == 0
