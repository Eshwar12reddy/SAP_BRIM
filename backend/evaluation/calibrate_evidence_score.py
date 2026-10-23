"""
Calibration Script for Strict KB-First RAG Evidence Scorer.

Evaluates at least 30 realistic questions (15 in-KB SAP BRIM/FI-CA questions and
15 out-of-KB SAP/general questions) against the SQLite knowledge base.
Reports evidence score distribution, gate results, and 0.75 threshold evaluation.
"""

import sys
import os
import statistics
from typing import List, Dict, Any

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.app.database import SessionLocal
from backend.app.config import settings
from backend.app.services.retrieval_service import retrieval_service
from backend.app.services.reranking_service import reranking_service
from backend.app.services.evidence_selection_service import evidence_selection_service

QUESTIONS = [
    # --- 15 In-KB SAP BRIM / FI-CA / CC / CI Questions ---
    "What is the lifecycle of billable items in SAP BRIM Convergent Invoicing?",
    "How does Convergent Charging rate and charge usage events for subscription contracts?",
    "Explain mass billing execution with transaction FKKBIX_BILL_M in Convergent Invoicing.",
    "How do invoicing reversal FKKINV_REV and billing reversal work in FI-CA?",
    "What is the role of reconciliation keys in FI-CA and how are totals records transferred to General Ledger?",
    "How are business partner master data and contract accounts replicated from SOM to CC and FI-CA?",
    "What is the difference between raw, billable, and billed items in SAP CI?",
    "How do dunning proposals and dunning activity runs operate in Contract Accounts Receivable and Payable?",
    "How does ODI contract distribution replicate subscription orders to SAP CC?",
    "What tables store billable items in SAP CI such as DFKKBIXBIT4 and DFKKBIXBIT0?",
    "How do payments and clearing work in FI-CA using transaction FP05 and FPY1?",
    "Explain the integration between Convergent Charging and Convergent Invoicing via CIT and BIT.",
    "What is a partner settlement process in SAP BRIM?",
    "How to handle billing exceptions in SAP Convergent Invoicing?",
    "How does allowance management work in SAP Convergent Charging for prepaid balances?",

    # --- 15 Out-of-KB SAP / Specialized / Non-BRIM Questions ---
    "How do I configure employee onboarding workflows in SAP SuccessFactors Employee Central?",
    "What are the best practices for catalog punchout integration in SAP Ariba?",
    "How do I set up SAP Transportation Management freight order tendering?",
    "How does SAP Extended Warehouse Management (EWM) handle wave picking and yard management?",
    "Explain SAP IBP supply chain planning algorithms for demand forecasting.",
    "How do I configure SAP Fieldglass statement of work approval matrices?",
    "What is the procedure for upgrading SAP BPC 10.1 NetWeaver to SAP Analytics Cloud?",
    "How do I configure variant configuration in SAP ECC Plant Maintenance?",
    "What is the difference between Python asyncio and multi-threading in web servers?",
    "How do I train a transformer model using PyTorch distributed data parallel?",
    "What are the tax filing deadlines for corporate entities in Delaware for 2026?",
    "How do I repair an automobile alternator on a Toyota Corolla?",
    "How does Kubernetes ingress controller route gRPC traffic?",
    "Explain the recipe and baking temperature for traditional sourdough bread.",
    "What are the safety requirements for lithium-ion battery transport under IATA regulations?",
]

def run_calibration():
    db = SessionLocal()
    print("=" * 80)
    print("RUNNING CALIBRATION OF KB EVIDENCE SCORER (Threshold = 0.75)")
    print("=" * 80)

    results: List[Dict[str, Any]] = []

    for i, q in enumerate(QUESTIONS, start=1):
        is_in_kb_expected = (i <= 15)
        # 1. Retrieval
        candidates = retrieval_service.hybrid_search(db, q, top_k=settings.TOP_K)
        # 2. Rerank
        top_chunks, rerank_score, _ = reranking_service.rerank_kb(q, candidates, top_n=settings.RERANK_TOP_K)
        # 3. Evidence Score
        eval_res = evidence_selection_service.compute_kb_evidence_score(
            q, top_chunks, threshold=0.75
        )
        score = eval_res["evidence_score"]
        gate_passed = eval_res["gate_passed"]
        passed = eval_res["passed"]
        reason = eval_res["fallback_reason"]

        results.append({
            "idx": i,
            "query": q,
            "expected_in_kb": is_in_kb_expected,
            "score": score,
            "gate_passed": gate_passed,
            "passed": passed,
            "reason": reason,
            "top_relevance": eval_res["signals"]["top_relevance"],
            "term_coverage": eval_res["signals"]["term_coverage"],
        })

        tag = "IN-KB" if is_in_kb_expected else "OUT-OF-KB"
        decision = "KB ANSWER" if passed else "TAVILY FALLBACK"
        print(f"[{i:02d}] [{tag}] Score: {score:.4f} | Gate: {str(gate_passed):<5} | Decision: {decision:<15} | Q: {q[:50]}...")
        if not passed:
            print(f"     -> Fallback reason: {reason}")

    db.close()

    # Summary statistics
    in_kb_scores = [r["score"] for r in results if r["expected_in_kb"]]
    out_kb_scores = [r["score"] for r in results if not r["expected_in_kb"]]
    all_scores = [r["score"] for r in results]

    in_kb_passed = sum(1 for r in results if r["expected_in_kb"] and r["passed"])
    out_kb_fallback = sum(1 for r in results if not r["expected_in_kb"] and not r["passed"])

    print("\n" + "=" * 80)
    print("CALIBRATION DISTRIBUTION & ANALYSIS")
    print("=" * 80)
    print(f"Total Questions Evaluated: {len(results)}")
    print(f"Overall Evidence Score Range: min={min(all_scores):.4f}, max={max(all_scores):.4f}, mean={statistics.mean(all_scores):.4f}, median={statistics.median(all_scores):.4f}")
    print(f"In-KB Questions (N={len(in_kb_scores)}):")
    print(f"  - Score min: {min(in_kb_scores):.4f}, max: {max(in_kb_scores):.4f}, mean: {statistics.mean(in_kb_scores):.4f}, median: {statistics.median(in_kb_scores):.4f}")
    print(f"  - Passed Threshold (>=0.75 & Gate): {in_kb_passed}/{len(in_kb_scores)} ({in_kb_passed/len(in_kb_scores):.0%})")
    print(f"Out-of-KB Questions (N={len(out_kb_scores)}):")
    print(f"  - Score min: {min(out_kb_scores):.4f}, max: {max(out_kb_scores):.4f}, mean: {statistics.mean(out_kb_scores):.4f}, median: {statistics.median(out_kb_scores):.4f}")
    print(f"  - Triggered Tavily Fallback: {out_kb_fallback}/{len(out_kb_scores)} ({out_kb_fallback/len(out_kb_scores):.0%})")

    # Threshold evaluation
    print("\nThreshold (0.75) Evaluation:")
    if out_kb_fallback == len(out_kb_scores) and in_kb_passed >= 12:
        print("  -> Result: 0.75 is an OPTIMAL operating threshold. It cleanly routes out-of-KB questions to Tavily (100% fallback rate) while allowing grounded in-KB questions to answer strictly from the knowledge base without unnecessary web queries.")
    elif in_kb_passed < 10:
        print("  -> Warning: 0.75 may be slightly over-triggering web fallback on complex scenario in-KB questions.")
    else:
        print(f"  -> In-KB pass rate: {in_kb_passed/len(in_kb_scores):.0%}, Out-of-KB fallback rate: {out_kb_fallback/len(out_kb_scores):.0%}")

if __name__ == "__main__":
    run_calibration()
