"""
Enterprise SAP BRIM Scenario Test Suite for Clyptus.AI.

Tests difficult SAP BRIM end-to-end scenarios covering:
1. Subscription Order Management (SOM) - contract lifecycle & replication
2. Convergent Charging (CC) - usage rating, allowances & charging failures
3. Convergent Invoicing (CI) - billable item (BIT) processing & mass billing runs (FKKBIX_BILL_M)
4. Contract Accounts Receivable and Payable (FI-CA) - payment clearing (FPY1, FP05)
5. FI-CA Dunning - proposals (FPVA), activity runs (FPVB), dunning locks
6. FI-CA Document & Invoicing Reversals - payment reversal (FP08), clearing reset (FP07), invoicing reversal (FKKINV_REV)
7. FI-CA to General Ledger (GL) Reconciliation - totals records (FPG1, FPG4), reconciliation keys (DFKKAK), and ACDOCA
8. Multi-source routing: Web Search First -> Knowledge Base Fallback -> Comprehensive Architectural Solution
"""

import pytest
from unittest.mock import Mock
import importlib

rag_module = importlib.import_module("backend.app.services.rag_service")
from backend.app.services.rag_service import rag_service
from backend.app.services.answer_planner import answer_planner
from backend.app.services.evidence_selection_service import evidence_selection_service as selector
from backend.app.services.sap_classifier import sap_classifier


def _mock_kb(score=0.9, text="SAP BRIM internal documentation for testing"):
    return [{
        "chunk_id": "kb-brim-1",
        "document_name": "SAP BRIM Enterprise Implementation Manual",
        "page_number": 45,
        "section": "Process Execution & Troubleshooting",
        "chunk_text": text,
        "score": score,
        "rerank_score": score,
    }]


def _mock_web(query: str, full_query: str = ""):
    text = f"Official SAP documentation for {query}. Explaining troubleshooting, transactions, configuration, and tables. {full_query}".strip()
    return [{
        "title": f"SAP Help Portal: {query}",
        "url": f"https://help.sap.com/docs/brim/{query.lower().replace(' ', '-')[:40]}",
        "domain": "help.sap.com",
        "snippet": text,
        "chunk_text": text,
        "source_type": "web",
        "authority_tier": 1,
        "score": 0.95,
        "rerank_score": 0.95,
    }]



def _mock_confidence(score=0.9):
    return {
        "confidence": score,
        "kb_relevance_score": score * 100,
        "should_trigger_tavily": False,
        "reason": "mocked relevance score",
    }


# ==============================================================================
# SCENARIO 1: SOM SUBSCRIPTION ORDER MANAGEMENT CONTRACT LIFECYCLE
# ==============================================================================
def test_som_contract_lifecycle_scenario(monkeypatch):
    query = "In SAP BRIM SOM, a subscription contract change with mid-cycle upgrade fails replication to CC. How do I troubleshoot the contract distribution and verify the provider contract in CC?"
    
    is_sap, reason = sap_classifier.classify(query)
    assert is_sap is True

    plan = answer_planner.plan_answer(query)
    assert plan["question_type"] in ("scenario", "troubleshooting")
    assert "Problem Analysis" in plan["instructions"]
    assert "Recommended Fixes" in plan["instructions"]

    # Verify Web search is prioritized
    monkeypatch.setattr(rag_module.query_rewriter, "resolve_query", lambda q, chat_history=None: {"is_follow_up": False, "resolved_query": q})
    search = Mock(return_value=_mock_web("SOM Subscription Contract Replication", query))
    monkeypatch.setattr(rag_module.web_search_service, "search_sap_authoritative", search)
    generate = Mock(return_value="""### 1. Problem Analysis
Mid-cycle contract upgrade in SOM failed replication via ODI to Convergent Charging.

### 2. Possible Root Causes
1. Cross-catalog mapping discrepancy between SOM and CC charge plans.
2. Locked provider contract or business partner in CC.

### 3. Step-by-Step Troubleshooting (Correct Order)
1. Check Order Distribution Infrastructure (ODI) monitor via SM37 / CRM_ODI_MONITOR.
2. Inspect application log in SLG1 (Object: CRM_ORDER, Sub-object: ODI).
3. Review CC Core Tool / Admin+ contract status.

### 4. Relevant SAP Components, Transactions, Logs & Configuration Checks
- Components: SOM, CC, CI
- Transactions: CRMD_ORDER, SLG1, SM37
- Tables: CRMD_ORDERADM_H, CRMD_ORDERADM_I

### 5. Recommended Fixes
Reprocess failed ODI steps and align charge plan parameters.

### 6. Validation and Prevention Steps
Verify contract status in CC Core Tool and simulate usage rating.""")
    monkeypatch.setattr(rag_module.llm_service, "generate_answer", generate)
    monkeypatch.setattr(rag_module.grounding_service, "verify_answer", lambda *a, **k: {"passes_grounding_gate": True, "grounding_score": 0.95, "verification_status": "evaluated", "claims": []})

    result = rag_service.process_query(None, query)
    assert result["source_type"] == "web"
    assert "Problem Analysis" in result["answer"]
    assert "Troubleshooting" in result["answer"]


# ==============================================================================
# SCENARIO 2: CONVERGENT CHARGING (CC) RATING & ALLOWANCE FAILURE
# ==============================================================================
def test_cc_rating_charging_failure_scenario(monkeypatch):
    query = "In SAP Convergent Charging, consumption items (CITs) fail rating due to expired allowance and missing tariff table entries. How do I isolate the root cause and re-rate them?"
    
    is_sap, _ = sap_classifier.classify(query)
    assert is_sap is True

    plan = answer_planner.plan_answer(query)
    assert plan["question_type"] in ("scenario", "troubleshooting")

    monkeypatch.setattr(rag_module.query_rewriter, "resolve_query", lambda q, chat_history=None: {"is_follow_up": False, "resolved_query": q})
    monkeypatch.setattr(rag_module.web_search_service, "search_sap_authoritative", lambda q: _mock_web("SAP Convergent Charging CITs rating failure expired allowance", query))
    monkeypatch.setattr(rag_module.llm_service, "generate_answer", lambda *a, **k: "### 1. Problem Analysis\nUnrated CITs accumulate due to expired allowances.\n### 5. Recommended Fixes\nUpdate tariff table in CC Core Tool.")
    monkeypatch.setattr(rag_module.grounding_service, "verify_answer", lambda *a, **k: {"passes_grounding_gate": True, "grounding_score": 0.92, "verification_status": "evaluated", "claims": []})

    result = rag_service.process_query(None, query)
    assert result["source_type"] == "web"
    assert result["web_search_used"] is True


# ==============================================================================
# SCENARIO 3: CONVERGENT INVOICING (CI) MASS BILLING RUN FAILURE (FKKBIX_BILL_M)
# ==============================================================================
def test_ci_mass_billing_run_failure_scenario(monkeypatch):
    query = "In SAP Convergent Invoicing, a mass billing run FKKBIX_BILL_M terminates with locked contract accounts and unbilled BITs in DFKKBIXBIT4. How do I clear the lock and safely resume the run?"

    is_sap, _ = sap_classifier.classify(query)
    assert is_sap is True

    plan = answer_planner.plan_answer(query)
    assert plan["question_type"] in ("scenario", "troubleshooting")

    monkeypatch.setattr(rag_module.query_rewriter, "resolve_query", lambda q, chat_history=None: {"is_follow_up": False, "resolved_query": q})
    monkeypatch.setattr(rag_module.web_search_service, "search_sap_authoritative", lambda q: _mock_web("SAP Convergent Invoicing Billing Run FKKBIX_BILL_M Lock", query))
    monkeypatch.setattr(rag_module.llm_service, "generate_answer", lambda *a, **k: "### 1. Problem Analysis\nFKKBIX_BILL_M stopped.\n### 3. Step-by-Step Troubleshooting (Correct Order)\nCheck locks in SM12 and DFKKOP.")
    monkeypatch.setattr(rag_module.grounding_service, "verify_answer", lambda *a, **k: {"passes_grounding_gate": True, "grounding_score": 0.94, "verification_status": "evaluated", "claims": []})

    result = rag_service.process_query(None, query)
    assert result["source_type"] == "web"


# ==============================================================================
# SCENARIO 4: FI-CA PAYMENT CLEARING RUN (FPY1 & FP05)
# ==============================================================================
def test_fica_payment_clearing_scenario(monkeypatch):
    query = "In SAP FI-CA, an automatic payment clearing run FPY1 fails to clear open customer receivables due to clearing locks on DFKKOP. How do I configure clearing rules and execute manual clearing via FP05?"

    is_sap, _ = sap_classifier.classify(query)
    assert is_sap is True

    plan = answer_planner.plan_answer(query)
    assert plan["question_type"] in ("scenario", "troubleshooting", "configuration")

    # When Web search returns empty, it falls back to Knowledge Base!
    monkeypatch.setattr(rag_module.query_rewriter, "resolve_query", lambda q, chat_history=None: {"is_follow_up": False, "resolved_query": q})
    monkeypatch.setattr(rag_module.web_search_service, "search_sap_authoritative", lambda q: [])
    monkeypatch.setattr(rag_service, "_retrieve_internal_evidence", lambda *a, **k: (_mock_kb(text="FI-CA payment clearing and clearing rules FPY1 FP05"), 0.88, _mock_confidence(0.88)))
    monkeypatch.setattr(rag_module.llm_service, "generate_answer", lambda *a, **k: "**Source: Knowledge Base**\n### 1. Problem Analysis\nClearing locks on DFKKOP prevented FPY1 clearing.")
    monkeypatch.setattr(rag_module.grounding_service, "verify_answer", lambda *a, **k: {"passes_grounding_gate": True, "grounding_score": 0.90, "verification_status": "evaluated", "claims": []})

    result = rag_service.process_query(None, query)
    assert result["source_type"] == "knowledge_base"
    assert result["is_in_rag_pipeline"] is True
    assert len(result["citations"]) > 0


# ==============================================================================
# SCENARIO 5: FI-CA DUNNING RUN SCENARIO (FPVA, FPVB)
# ==============================================================================
def test_fica_dunning_run_scenario(monkeypatch):
    query = "In SAP FI-CA, the dunning proposal run FPVA completes with errors and does not create dunning notices for overdue contract accounts. How do I check dunning locks and execute FPVB?"

    is_sap, _ = sap_classifier.classify(query)
    assert is_sap is True

    monkeypatch.setattr(rag_module.query_rewriter, "resolve_query", lambda q, chat_history=None: {"is_follow_up": False, "resolved_query": q})
    monkeypatch.setattr(rag_module.web_search_service, "search_sap_authoritative", lambda q: _mock_web("SAP FI-CA Dunning FPVA FPVB", query))
    monkeypatch.setattr(rag_module.llm_service, "generate_answer", lambda *a, **k: "### 1. Problem Analysis\nDunning proposal FPVA missing notices.\n### 4. Relevant SAP Components\nTransactions: FPVA, FPVB. Tables: FKKMAKO, FKKMAZE.")
    monkeypatch.setattr(rag_module.grounding_service, "verify_answer", lambda *a, **k: {"passes_grounding_gate": True, "grounding_score": 0.91, "verification_status": "evaluated", "claims": []})

    result = rag_service.process_query(None, query)
    assert result["source_type"] == "web"


# ==============================================================================
# SCENARIO 6: FI-CA REVERSALS SCENARIO (FP08, FP07, FKKINV_REV)
# ==============================================================================
def test_fica_reversals_scenario(monkeypatch):
    query = "A customer invoice was incorrectly created in SAP CI and paid in FI-CA. What is the exact sequence to reset clearing via FP07, reverse the payment document via FP08, reverse the invoicing document via FKKINV_REV, and return BITs to raw status?"

    is_sap, _ = sap_classifier.classify(query)
    assert is_sap is True

    plan = answer_planner.plan_answer(query)
    assert plan["question_type"] in ("scenario", "troubleshooting", "integration")

    monkeypatch.setattr(rag_module.query_rewriter, "resolve_query", lambda q, chat_history=None: {"is_follow_up": False, "resolved_query": q})
    monkeypatch.setattr(rag_module.web_search_service, "search_sap_authoritative", lambda q: _mock_web("SAP CI and FI-CA reversal FP07 FP08 FKKINV_REV BITs", query))
    monkeypatch.setattr(rag_module.llm_service, "generate_answer", lambda *a, **k: "### 3. Step-by-Step Troubleshooting (Correct Order)\n1. Reset clearing with FP07.\n2. Reverse payment document with FP08.\n3. Reverse invoicing document with FKKINV_REV.\n4. Restore BIT status in DFKKBIXBIT4.")
    monkeypatch.setattr(rag_module.grounding_service, "verify_answer", lambda *a, **k: {"passes_grounding_gate": True, "grounding_score": 0.95, "verification_status": "evaluated", "claims": []})

    result = rag_service.process_query(None, query)
    assert result["source_type"] == "web"
    assert "FP07" in result["answer"]
    assert "FP08" in result["answer"]


# ==============================================================================
# SCENARIO 7: FI-CA TO GENERAL LEDGER (GL) RECONCILIATION SCENARIO (FPG1, FPG4)
# ==============================================================================
def test_fica_gl_reconciliation_scenario(monkeypatch):
    query = "During month-end closing, an FI-CA reconciliation key fails transfer to General Ledger with error in FPG4. How do I reconcile DFKKAK totals records against ACDOCA and correct open reconciliation keys?"

    is_sap, _ = sap_classifier.classify(query)
    assert is_sap is True

    plan = answer_planner.plan_answer(query)
    assert plan["question_type"] in ("scenario", "troubleshooting")

    monkeypatch.setattr(rag_module.query_rewriter, "resolve_query", lambda q, chat_history=None: {"is_follow_up": False, "resolved_query": q})
    monkeypatch.setattr(rag_module.web_search_service, "search_sap_authoritative", lambda q: _mock_web("SAP FI-CA reconciliation key FPG4 DFKKAK General Ledger ACDOCA", query))
    monkeypatch.setattr(rag_module.llm_service, "generate_answer", lambda *a, **k: "### 1. Problem Analysis\nFPG4 transfer error for reconciliation key.\n### 4. Relevant SAP Components\nTransactions: FPG1, FPG4, FPG0. Tables: DFKKAK, DFKKKO, ACDOCA.")
    monkeypatch.setattr(rag_module.grounding_service, "verify_answer", lambda *a, **k: {"passes_grounding_gate": True, "grounding_score": 0.96, "verification_status": "evaluated", "claims": []})

    result = rag_service.process_query(None, query)
    assert result["source_type"] == "web"


# ==============================================================================
# SCENARIO 8: STRICT EVIDENCE ABSTENTION WHEN SOURCES ARE UNAVAILABLE
# ==============================================================================
def test_no_dead_end_refusal_when_sources_unavailable(monkeypatch):
    """
    When web search returns empty and knowledge base has no documents,
    the chatbot must strictly abstain rather than guessing or fabricating.
    """
    query = "In SAP BRIM Convergent Invoicing, how do I configure BIT class activation and test rating in CC?"

    monkeypatch.setattr(rag_module.query_rewriter, "resolve_query", lambda q, chat_history=None: {"is_follow_up": False, "resolved_query": q})
    monkeypatch.setattr(rag_module.web_search_service, "search_sap_authoritative", lambda q: [])
    monkeypatch.setattr(rag_service, "_retrieve_internal_evidence", lambda *a, **k: ([], 0.0, _mock_confidence(0.0)))

    result = rag_service.process_query(None, query)
    assert result["source_type"] == "insufficient"
    assert "could not verify this sap answer to the required confidence level" in result["answer"].lower()
