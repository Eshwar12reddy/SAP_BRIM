import json

from backend.app.services.grounding_service import GroundingService


KB_EVIDENCE = [{
    "source_id": "kb-1",
    "source_type": "knowledge_base",
    "document_name": "SAP BRIM Guide",
    "page_number": 12,
    "section": "Charging",
    "chunk_text": "SAP Convergent Charging rates usage events and calculates charges.",
}]


def mock_judgement(monkeypatch, claims):
    from backend.app.services.llm_service import llm_service

    monkeypatch.setattr(
        llm_service,
        "generate_completion",
        lambda prompt, system_prompt=None: json.dumps({"claims": claims}),
    )


def test_grounding_score_for_fully_supported_answer(monkeypatch):
    mock_judgement(monkeypatch, [{
        "claim": "SAP Convergent Charging rates usage events.",
        "status": "supported",
        "evidence_ids": ["kb-1"],
        "reason": "The passage states this directly.",
    }])

    result = GroundingService().verify_answer(
        "What does SAP Convergent Charging do?",
        "SAP Convergent Charging rates usage events.",
        KB_EVIDENCE,
    )

    assert result["grounding_score"] == 1.0
    assert result["kb_grounding_score"] == 1.0
    assert result["web_grounding_score"] is None
    assert result["claims"][0]["supporting_evidence"][0]["source_type"] == "knowledge_base"


def test_grounding_score_decreases_for_partially_supported_answer(monkeypatch):
    mock_judgement(monkeypatch, [
        {
            "claim": "SAP Convergent Charging rates usage events.",
            "status": "supported",
            "evidence_ids": ["kb-1"],
            "reason": "Directly stated.",
        },
        {
            "claim": "SAP Convergent Charging calculates all charge types.",
            "status": "partially_supported",
            "evidence_ids": ["kb-1"],
            "reason": "The passage supports rating usage events but not all charge types.",
        },
        {
            "claim": "SAP Convergent Charging posts invoices to FI-CA.",
            "status": "unsupported",
            "evidence_ids": [],
            "reason": "The passage does not discuss FI-CA postings.",
        },
    ])

    result = GroundingService().verify_answer(
        "Explain charging and posting.",
        "SAP Convergent Charging rates usage events. SAP Convergent Charging posts invoices to FI-CA.",
        KB_EVIDENCE,
    )

    assert result["grounding_score"] == 0.5
    assert len(result["supported_claims"]) == 1
    assert len(result["partially_supported_claims"]) == 1
    assert len(result["unsupported_claims"]) == 1


def test_unsupported_claims_score_zero(monkeypatch):
    mock_judgement(monkeypatch, [{
        "claim": "SAP Convergent Charging calculates tax.",
        "status": "unsupported",
        "evidence_ids": [],
        "reason": "The passage does not mention tax.",
    }])

    result = GroundingService().verify_answer(
        "What does the product do?",
        "SAP Convergent Charging calculates tax.",
        KB_EVIDENCE,
    )

    assert result["grounding_score"] == 0.0
    assert result["verification_status"] == "unverified"


def test_web_only_evidence_does_not_become_kb_grounding(monkeypatch):
    mock_judgement(monkeypatch, [{
        "claim": "SAP Convergent Charging rates usage events.",
        "status": "supported",
        "evidence_ids": ["web-1"],
        "reason": "The web passage states this directly.",
    }])
    web_evidence = [{
        "source_id": "web-1",
        "source_type": "web",
        "title": "SAP Help",
        "url": "https://help.sap.com/example",
        "snippet": "SAP Convergent Charging rates usage events.",
    }]

    result = GroundingService().verify_answer(
        "What does SAP Convergent Charging do?",
        "SAP Convergent Charging rates usage events.",
        web_evidence,
        source_type="web",
    )

    assert result["grounding_score"] == 1.0
    assert result["kb_grounding_score"] is None
    assert result["web_grounding_score"] == 1.0


def test_mixed_claims_keep_grounding_provenance_separate(monkeypatch):
    mock_judgement(monkeypatch, [
        {
            "claim": "Charging rates usage events.",
            "status": "supported",
            "evidence_ids": ["kb-1"],
            "reason": "Supported by the knowledge-base passage.",
        },
        {
            "claim": "Charging supports usage import through a web-documented API.",
            "status": "supported",
            "evidence_ids": ["web-1"],
            "reason": "Supported by the supplied web passage.",
        },
    ])
    mixed_evidence = KB_EVIDENCE + [{
        "source_id": "web-1",
        "source_type": "web",
        "title": "SAP Help",
        "url": "https://help.sap.com/example",
        "snippet": "Charging supports usage import through a web-documented API.",
    }]

    result = GroundingService().verify_answer(
        "Explain charging.",
        "Charging rates usage events. Charging supports usage import through a web-documented API.",
        mixed_evidence,
        source_type="combined",
    )

    assert result["grounding_score"] == 1.0
    assert result["kb_grounding_score"] == 0.5
    assert result["web_grounding_score"] == 0.5


def test_missing_or_invalid_evaluator_result_is_not_scored(monkeypatch):
    from backend.app.services.llm_service import llm_service

    monkeypatch.setattr(
        llm_service,
        "generate_completion",
        lambda prompt, system_prompt=None: "not json",
    )
    service = GroundingService()

    failed = service.verify_answer("Question?", "Factual answer.", KB_EVIDENCE)
    missing = service.verify_answer("Question?", "Factual answer.", [])

    assert failed["grounding_score"] is None
    assert failed["grounding_status"] == "evaluation_failed"
    assert missing["grounding_score"] is None
    assert missing["grounding_status"] == "insufficient_evidence"
