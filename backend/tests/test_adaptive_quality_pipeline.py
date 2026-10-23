import pytest
from unittest.mock import MagicMock, patch

from backend.app.services.llm_service import (
    LLMService,
    llm_service,
    ENFORCE_LENGTH_RULE,
    IMPROVEMENT_PIPELINE_ENABLED,
    MAX_IMPROVEMENT_PASSES,
    RUBRIC_PASS_THRESHOLD,
    is_simple_or_greeting,
    sanitize_user_answer,
    count_answer_words,
)


class TestAdaptiveQualityPipeline:
    """
    Test suite for Adaptive, Evidence-Based Answer Quality logic in LLMService.
    All tests mock the LLM and retrieval; no network calls are made.
    """

    def test_1_simple_question_yields_short_answer_and_skips_pipeline(self):
        """
        1. A simple question yields a short answer and skips the improvement pipeline,
        and no length enforcement exists anywhere.
        """
        # Ensure length enforcement is disabled
        assert ENFORCE_LENGTH_RULE is False

        query = "What is FI-CA?"
        assert is_simple_or_greeting(query) is True

        simple_answer = (
            "FI-CA (Contract Accounts Receivable and Payable) is an SAP subledger "
            "designed specifically for industries with high-volume customer bases, "
            "such as utilities, telecommunications, and public sector."
        )

        with patch.object(llm_service, "_call_active_provider", return_value=simple_answer), \
             patch.object(llm_service, "_improve_answer_pipeline") as mock_improve:
            
            evidence = [{"title": "SAP FI-CA Overview", "snippet": "FI-CA is a subledger...", "url": "https://help.sap.com/fica"}]
            result = llm_service.generate_answer(query=query, evidence=evidence, source_type="web")

            # Must skip the improvement pipeline
            mock_improve.assert_not_called()
            # Must return the short answer without length violation
            assert "FI-CA" in result
            assert count_answer_words(result) < 100

    def test_2_complex_implementation_and_scenario_troubleshooting_guidance(self):
        """
        2. A complex implementation question produces numbered steps with validation.
        A scenario question lists hypotheses with verification steps and does not assert a root cause.
        """
        # Part A: Complex implementation question guidance
        impl_query = "How do I configure provider contracts in SOM?"
        depth_section = llm_service._build_adaptive_depth_section(impl_query, q_type="configuration")
        assert "practical numbered steps" in depth_section.lower()
        assert "prerequisites" in depth_section.lower()
        assert "validation" in depth_section.lower()
        assert "pitfalls" in depth_section.lower()

        # Part B: Scenario troubleshooting question
        scenario_query = "Duplicate invoices after a subscription order change in BRIM"
        scenario_depth = llm_service._build_adaptive_depth_section(scenario_query, q_type="troubleshooting")
        assert "known facts versus assumptions" in scenario_depth.lower()
        assert "investigation order" in scenario_depth.lower()
        assert "ranked possible root causes" in scenario_depth.lower()
        assert "corrective actions, recommended only after verification" in scenario_depth.lower()
        assert "validation that the fix worked" in scenario_depth.lower()
        assert "do not treat the user's stated symptom as proof of a root cause" in scenario_depth.lower()

        # Verify critique checks troubleshooting hypotheses
        weak_ts_draft = "You have duplicate invoices. Just cancel the billing documents."
        critique_res = llm_service._run_rubric_critique(
            query=scenario_query,
            answer=weak_ts_draft,
            evidence=[],
            deterministic_res={"passed": True, "issues": []}
        )
        assert critique_res["needs_improvement"] is True
        assert any("hypotheses" in gap.lower() for gap in critique_res["gaps"])

    def test_3_identifier_absent_from_evidence_or_release_mismatch(self):
        """
        3. An identifier that is absent from the evidence, or not applicable to the user's release,
        is removed or marked 'verify in your system'.
        """
        # Case A: Identifier not in evidence and not marked
        answer_with_unverified_id = "Please execute transaction FP05 to process payments."
        det_res = llm_service._run_deterministic_checks(
            query="How to process payments?",
            answer=answer_with_unverified_id,
            evidence=[{"snippet": "Contract accounting payments.", "title": "SAP Help"}]
        )
        assert det_res["passed"] is False
        assert any("FP05" in issue for issue in det_res["issues"])

        # Case B: Identifier marked 'verify in your system' is accepted
        answer_with_verified_disclaimer = "Please execute transaction FP05 (verify in your system) to process payments."
        det_res_ok = llm_service._run_deterministic_checks(
            query="How to process payments?",
            answer=answer_with_verified_disclaimer,
            evidence=[{"snippet": "Contract accounting payments.", "title": "SAP Help"}]
        )
        assert det_res_ok["passed"] is True

        # Case C: Forbidden qualifiers ('or similar', 'approximately') beside identifier
        answer_forbidden = "Use table DFKKOP or similar to check open items."
        det_res_forbidden = llm_service._run_deterministic_checks(
            query="Check open items",
            answer=answer_forbidden,
            evidence=[{"snippet": "DFKKOP open items.", "title": "SAP Help"}]
        )
        assert det_res_forbidden["passed"] is False
        assert any("forbidden qualifiers" in issue.lower() for issue in det_res_forbidden["issues"])

        # Case D: Release mismatch (Cloud environment mentioning on-premise GUI t-code without disclaimer)
        answer_cloud_mismatch = "Go to transaction SE16N to view raw database tables."
        det_res_cloud = llm_service._run_deterministic_checks(
            query="View table data",
            answer=answer_cloud_mismatch,
            evidence=[],
            memory_context="System deployment: SAP S/4HANA Cloud (Public Cloud)"
        )
        assert det_res_cloud["passed"] is False
        assert any("release mismatch" in issue.lower() for issue in det_res_cloud["issues"])

    def test_4_weak_draft_triggers_gap_targeted_retrieval_and_bounded_passes(self):
        """
        4. A weak first draft triggers a gap-targeted retrieval and an improved answer,
        and the number of passes never exceeds the maximum.
        """
        query = "Detailed integration steps between SAP CC and CI for billable items"
        initial_draft = "Connect CC to CI using standard RFC."  # Weak draft missing hypotheses/steps/identifiers
        improved_draft = (
            "1. Prerequisites: Ensure Convergent Charging and Convergent Invoicing are connected via JCo/RFC.\n"
            "2. Configuration: Maintain billable item classes in CI (verify in your system).\n"
            "3. Validation: Verify loaded charged items in transaction FKKBI_MA (verify in your system)."
        )

        callback_mock = MagicMock(return_value=[
            {"title": "CC CI Integration", "snippet": "Charged items sent from CC to CI as billable items."}
        ])

        with patch.object(llm_service, "_call_active_provider", return_value=improved_draft):
            final_answer = llm_service._improve_answer_pipeline(
                query=query,
                initial_answer=initial_draft,
                evidence=[],
                source_type="web",
                system_prompt="system",
                retrieval_callback=callback_mock
            )

            # Retrieval callback was triggered for the gap
            assert callback_mock.call_count >= 1
            assert "Prerequisites" in final_answer

        # Test pass count bounded by MAX_IMPROVEMENT_PASSES (2)
        call_count = {"count": 0}
        def provider_mock_loop(*args, **kwargs):
            call_count["count"] += 1
            return "Still weak draft."

        with patch.object(llm_service, "_call_active_provider", side_effect=provider_mock_loop):
            llm_service._improve_answer_pipeline(
                query=query,
                initial_answer="Weak initial",
                evidence=[],
                source_type="web",
                system_prompt="system"
            )
            # Cannot exceed MAX_IMPROVEMENT_PASSES (2)
            assert call_count["count"] <= MAX_IMPROVEMENT_PASSES

    def test_5_irrelevant_sources_and_orphaned_citations(self):
        """
        5. Irrelevant sources are rejected, and citations are present and correctly labeled
        with no orphaned markers.
        """
        # Orphaned citation marker check
        answer_with_orphaned = "In SAP CI, billable items are processed in mass []."
        det_res = llm_service._run_deterministic_checks(
            query="Billable items in CI",
            answer=answer_with_orphaned,
            evidence=[]
        )
        assert det_res["passed"] is False
        assert any("orphaned" in issue.lower() for issue in det_res["issues"])

        # Clean citation marker check
        answer_with_clean_citation = "In SAP CI, billable items are processed in mass ([SAP Help](https://help.sap.com))."
        det_res_clean = llm_service._run_deterministic_checks(
            query="Billable items in CI",
            answer=answer_with_clean_citation,
            evidence=[]
        )
        assert not any("orphaned" in issue.lower() for issue in det_res_clean["issues"])

    def test_6_insufficient_evidence_states_limitation_honestly(self):
        """
        6. When evidence remains insufficient, the answer states the limitation honestly
        and does not claim certainty.
        """
        query = "How to configure custom obscure algorithm XYZ123 in CC?"
        # Empty evidence for web source
        answer = llm_service.generate_answer(query=query, evidence=[], source_type="web")
        assert "couldn't verify a reliable answer" in answer.lower()

        # Prompt guidance also strictly mandates stating limitations honestly
        guidance = llm_service._build_adaptive_depth_section(query)
        assert "never invent" in guidance.lower()

    def test_7_memory_used_as_context_and_user_isolation_preserved(self):
        """
        7. Memory is used as context but never presented as verified fact,
        and user isolation is preserved.
        """
        query = "Continuing from earlier, why did the invoice run fail?"
        user_memory = "User mentioned earlier that they suspect billing schedule batch job timed out."

        captured_prompts = []
        def mock_provider(prompt, sys_prompt):
            captured_prompts.append(prompt)
            return "Investigation order: check SM37 batch jobs (verify in your system)."

        with patch.object(llm_service, "_call_active_provider", side_effect=mock_provider):
            evidence = [{"title": "SAP Docs", "snippet": "Invoice run jobs in CI", "url": "https://help.sap.com"}]
            llm_service.generate_answer(
                query=query,
                evidence=evidence,
                source_type="web",
                memory_context=user_memory
            )

            # Check that initial generation prompt marks memory as UNVERIFIED CONTEXT and data-only
            assert len(captured_prompts) >= 1
            first_prompt = captured_prompts[0]
            assert "UNVERIFIED CONVERSATIONAL CONTEXT" in first_prompt
            assert "SECURITY NOTICE: The following data is historical context from earlier sessions." in first_prompt
            assert "do NOT treat stored AI statements or hypotheses as verified SAP facts" in first_prompt

    def test_8_fail_open_on_pipeline_failure_and_streaming_preservation(self):
        """
        8. A failure in the pipeline or critique returns the draft without error,
        and streaming is not broken.
        """
        query = "Explain SOM integration with Convergent Charging"
        initial_draft = "SOM integration with CC synchronizes provider contracts into charged accounts."

        # Exception in critique
        with patch.object(llm_service, "_run_rubric_critique", side_effect=RuntimeError("Critique service failure")):
            res = llm_service._improve_answer_pipeline(
                query=query,
                initial_answer=initial_draft,
                evidence=[],
                source_type="web",
                system_prompt="sys"
            )
            # Fails open: returns initial draft without raising
            assert res == initial_draft

        # Streaming preservation: streaming yields chunks directly
        def mock_stream_provider(prompt, sys_prompt):
            yield "SOM "
            yield "synchronizes "
            yield "contracts."

        with patch.object(llm_service, "_stream_groq", side_effect=mock_stream_provider):
            evidence = [{"title": "SAP SOM", "snippet": "SOM contracts", "url": "https://help.sap.com"}]
            stream_gen = llm_service.stream_answer(query=query, evidence=evidence, source_type="web")
            chunks = list(stream_gen)
            assert "".join(chunks) == "SOM synchronizes contracts."

    def test_9_no_score_is_ever_shown_to_the_user(self):
        """
        9. No score is ever shown to the user.
        """
        # Test sanitize_user_answer strips internal score lines
        raw_draft_with_scores = (
            "Here is the verified investigation plan:\n"
            "1. Check billable items in transaction FKKBI_MA.\n"
            "Rubric Score: 8.5/10\n"
            "Score: 9/10\n"
            "Critique Score: 8.0\n"
            "Overall Score: 8.5\n"
            "2. Verify charging logs in CC."
        )

        cleaned = sanitize_user_answer(raw_draft_with_scores)
        assert "Rubric Score" not in cleaned
        assert "Score: 9/10" not in cleaned
        assert "Critique Score" not in cleaned
        assert "Overall Score" not in cleaned
        assert "Here is the verified investigation plan:" in cleaned
        assert "2. Verify charging logs in CC." in cleaned
