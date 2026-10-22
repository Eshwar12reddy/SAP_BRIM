import json
import uuid
import pytest
from unittest.mock import MagicMock, patch

from backend.app.config import settings
from backend.app.services.sap_classifier import sap_classifier
from backend.app.services.answer_planner import answer_planner
from backend.app.services.evidence_selection_service import evidence_selection_service
from backend.app.services.memory_service import memory_service
from backend.app.services.rag_service import rag_service
from backend.app.models.user import User
from backend.app.models.memory import SAPScenarioMemory


QUERY = (
    "A customer subscription was cancelled on 30 September, but recurring invoices continued in October and November. "
    "Trace the investigation through SOM, CC, CI, and FI-CA. "
    "Identify possible root causes, diagnostic checks, corrective actions, and supporting evidence."
)


def test_subscription_cancellation_in_scope():
    """Verify that the subscription cancellation question passes SAP scope classification."""
    is_sap, reason = sap_classifier.classify(QUERY)
    assert is_sap is True


def test_evidence_score_calibrated_against_scenario_noise():
    """
    Verify that temporal scenario terms (30, September, October, November)
    do not deflate term coverage or evidence score below the 0.75 threshold.
    """
    kb_chunks = [
        {
            "chunk_id": "chunk_som_1",
            "document_name": "BRIM_SOM_Contract_Management.pdf",
            "page_number": 120,
            "section": "Contract Cancellation & Deactivation",
            "chunk_text": (
                "When a subscription contract is cancelled in SOM, the contract item validity is updated "
                "with an effective cancellation end date and distributed via ODI to SAP CC and CI. "
                "If distribution fails or contract status is not updated, recurring billing plans continue."
            ),
            "score": 0.82,
            "rerank_score": 0.82,
        },
        {
            "chunk_id": "chunk_ci_1",
            "document_name": "BRIM_CI_Invoicing_Guide.pdf",
            "page_number": 88,
            "section": "Recurring Billing Plans & BIT Generation",
            "chunk_text": (
                "In Convergent Invoicing, recurring fees are generated from billing plans into billable items (BITs). "
                "Invoicing runs process BITs into invoicing documents and post receivables to FI-CA. "
                "Reversal of incorrectly generated documents is performed using transaction FKKINV_REV."
            ),
            "score": 0.80,
            "rerank_score": 0.80,
        },
        {
            "chunk_id": "chunk_fica_1",
            "document_name": "BRIM_FICA_Receivables.pdf",
            "page_number": 204,
            "section": "Open Items & Account Balance",
            "chunk_text": (
                "FI-CA manages posted receivables, open items in DFKKOP, and reconciliation keys. "
                "Invoicing documents create contract account receivables, and reversals clear open items."
            ),
            "score": 0.78,
            "rerank_score": 0.78,
        },
    ]

    eval_result = evidence_selection_service.compute_kb_evidence_score(QUERY, kb_chunks, threshold=0.75)
    
    # Evidence score must achieve threshold (>= 0.75) without artificial threshold lowering
    assert eval_result["evidence_score"] >= 0.75, f"Expected evidence score >= 0.75, got {eval_result['evidence_score']}"
    assert eval_result["gate_passed"] is True
    assert eval_result["passed"] is True
    # Verify key tokens exclude temporal noise
    query_tokens = evidence_selection_service._extract_query_tokens(QUERY)
    assert "30" not in query_tokens
    assert "september" not in query_tokens
    assert "october" not in query_tokens
    assert "november" not in query_tokens
    assert "subscription" in query_tokens
    assert "cancelled" in query_tokens


def test_cross_chat_memory_does_not_inject_unrelated_duplicate_invoices():
    """
    Verify that an unrelated prior scenario memory ('Duplicate Invoices in CI')
    is NOT condensed or injected into the subscription cancellation query.
    """
    mock_db = MagicMock()
    user_id = str(uuid.uuid4())

    # Simulate an existing open scenario memory about duplicate invoices
    old_scenario = SAPScenarioMemory(
        id=str(uuid.uuid4()),
        user_id=user_id,
        scenario_title="Duplicate Invoices after Subscription Order Change in SOM",
        symptoms="Duplicate billable items in DFKKBIXBIT2 causing duplicate CI invoices.",
        status="open",
    )
    
    retrieved_res = {
        "used_memories": [],
        "used_memory_ids": [],
        "formatted_context": "",
        "previous_context_used": False,
        "top_scenario": old_scenario,
    }

    # Query condensation must NOT rewrite the 27-word standalone subscription cancellation query
    condensed = memory_service.condense_query_with_memory(QUERY, retrieved_res)
    assert condensed == QUERY
    assert "Duplicate Invoices" not in condensed


def test_subscription_cancellation_investigation_plan_generation():
    """
    Verify that the pipeline produces a structured first-pass investigation plan
    covering SOM, CC, CI, and FI-CA without demanding product version details upfront.
    """
    mock_db = MagicMock()
    user = User(id=str(uuid.uuid4()), email="architect@sap.com", role="consultant", memory_enabled=True)

    kb_evidence = [
        {
            "chunk_id": "chunk-som-01",
            "title": "SOM Contract Item Validity Guide",
            "document_name": "SOM_Contract_Item_Validity.pdf",
            "url": "https://help.sap.com/docs/som-cancellation",
            "chunk_text": "Subscription contract cancellation in SOM sets effective deactivation date and triggers ODI distribution logged in transaction SLG1.",
            "snippet": "Subscription contract cancellation in SOM sets effective deactivation date and triggers ODI distribution logged in transaction SLG1.",
            "page_number": 45,
            "score": 0.85,
            "source_type": "knowledge_base",
        },
        {
            "chunk_id": "chunk-cc-01",
            "title": "SAP Convergent Charging Provider Contract Guide",
            "document_name": "CC_Provider_Contracts.pdf",
            "url": "https://help.sap.com/docs/cc-provider-contracts",
            "chunk_text": "In SAP CC, provider contract validity and charge-plan deactivation determine whether recurring or usage-based charges are rated.",
            "snippet": "In SAP CC, provider contract validity and charge-plan deactivation determine whether recurring or usage-based charges are rated.",
            "page_number": 62,
            "score": 0.84,
            "source_type": "knowledge_base",
        },
        {
            "chunk_id": "chunk-ci-01",
            "title": "Convergent Invoicing Recurring Billing Plans",
            "document_name": "CI_Billing_Plans.pdf",
            "url": "https://help.sap.com/docs/ci-recurring-billing",
            "chunk_text": "Recurring billing plans generate BITs in tables DFKKBIXBIT0 and DFKKBIXBIT2 for mass billing runs FKKBIX_BILL_M and invoicing runs FKKINV_M. Reversal uses transaction FKKINV_REV.",
            "snippet": "Recurring billing plans generate BITs in tables DFKKBIXBIT0 and DFKKBIXBIT2 for mass billing runs FKKBIX_BILL_M and invoicing runs FKKINV_M. Reversal uses transaction FKKINV_REV.",
            "page_number": 88,
            "score": 0.83,
            "source_type": "knowledge_base",
        },
        {
            "chunk_id": "chunk-fica-01",
            "title": "FI-CA Open Item Management",
            "document_name": "FICA_Receivables.pdf",
            "url": "https://help.sap.com/docs/fica-receivables",
            "chunk_text": "Invoicing posts receivables to contract accounts in DFKKOP with invoice reference. Clearing can be reset using transaction FP07.",
            "snippet": "Invoicing posts receivables to contract accounts in DFKKOP with invoice reference. Clearing can be reset using transaction FP07.",
            "page_number": 120,
            "score": 0.81,
            "source_type": "knowledge_base",
        },
    ]

    expected_answer = """### Investigation Plan: Post-Cancellation Recurring Invoices

#### 1. Problem Analysis & Investigation Scope
A subscription cancelled effective 30 September continued generating recurring invoices in October and November.
The investigation follows the SAP BRIM integration chain to identify where the cancellation status failed to take effect.

#### 2. Component-by-Component Investigation Areas

##### A. Subscription Order Management (SOM)
- **Investigation areas**: Verify cancellation status on the subscription contract item and effective end date.
- **Diagnostic checks**: Confirm whether the cancellation change order successfully distributed via Order Distribution Infrastructure (ODI) or remains stuck in status 'In Distribution'.
- **Evidence**: Check contract item validity dates and ODI message log in SLG1 (object `CRM_ORDER`, sub-object `ODI`).

##### B. SAP Convergent Charging (CC)
- **Investigation areas**: Provider contract validity and charge-plan deactivation in CC Core Tool.
- **Diagnostic checks**: Determine whether usage-based or recurring charges were rated post-30 September, and whether charging trees reflect the deactivation date.
- **Evidence**: CC Core Tool contract state and rater logs.

##### C. SAP Convergent Invoicing (CI)
- **Investigation areas**: Recurring billing-plan validity, unbilled Billable Items (BITs), and mass billing runs.
- **Diagnostic checks**: Check whether recurring billing plans were closed or continued generating BITs in table `DFKKBIXBIT0`/`DFKKBIXBIT2`. Verify billing run logs (`FKKBIX_BILL_M`) and invoicing run logs (`FKKINV_M`).
- **Corrective actions**: Execute invoicing reversal with transaction `FKKINV_REV` and billing document reversal.

##### D. Contract Accounts Receivable and Payable (FI-CA)
- **Investigation areas**: Posted receivables, invoice references, clearing status, and open items in `DFKKOP`.
- **Diagnostic checks**: Review customer contract account balance, verify invoice documents, and check whether payments were auto-cleared.
- **Corrective actions**: Reverse FI-CA documents, reset clearing (`FP07`), or issue credit memo.

#### 3. Summary of Supporting vs Missing Evidence
- **Supported by KB evidence**: SOM cancellation distribution workflow, CI billing plan BIT generation, `FKKINV_REV` reversal process, FI-CA `DFKKOP` receivables.
- **Missing system-specific evidence**: Specific customer contract number, ODI error status code, and whether October/November BITs originated from usage rating or recurring billing plans."""

    with patch.object(rag_service, "_search_with_kb_fallback") as mock_search:
        mock_search.return_value = (
            {
                "selected_passages": kb_evidence,
                "source_type": "knowledge_base",
                "evidence_score": 0.83,
                "is_sufficient": True,
                "needs_web_fallback": False,
                "candidate_passages": kb_evidence,
            },
            [],
            False,
            kb_evidence,
            {"confidence": 0.83, "evidence_score": 0.83},
        )
        with patch("backend.app.services.rag_service.llm_service.generate_answer", return_value=expected_answer):
            res = rag_service.process_query(mock_db, QUERY, user=user)

            assert res["source_type"] == "knowledge_base"
            assert res["answer"] != ""
            answer_text = res["answer"]

            # Must NOT demand version details upfront
            assert "specific sap product and deployment model (e.g., sap s/4hana vs sap ecc vs sap brim)" not in answer_text.lower()

            # Must cover all 4 architectural components
            assert "som" in answer_text.lower()
            assert "cc" in answer_text.lower() or "convergent charging" in answer_text.lower()
            assert "ci" in answer_text.lower() or "convergent invoicing" in answer_text.lower()
            assert "fi-ca" in answer_text.lower() or "fica" in answer_text.lower()

            # Must present investigation areas and diagnostic checks
            assert "cancellation" in answer_text.lower()
            assert "contract" in answer_text.lower()
            assert "fkkinv_rev" in answer_text.lower() or "reversal" in answer_text.lower()
            assert "dfkkop" in answer_text.lower() or "receivables" in answer_text.lower() or "open item" in answer_text.lower()

            # Citations must be populated
            assert len(res["citations"]) > 0
            # Must not contain duplicate invoice scenario title
            assert "duplicate invoices after subscription order change" not in answer_text.lower()
