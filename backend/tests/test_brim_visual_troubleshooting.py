import pytest
import xml.etree.ElementTree as ET
from backend.app.services.visual.sap_gui_svg_builder import sap_gui_svg_builder, SapGuiSvgBuilder
from backend.app.services.brim_troubleshooting_service import brim_troubleshooting_service, BrimTroubleshootingService
from backend.app.services.answer_planner import answer_planner
from backend.app.services.llm_service import llm_service


class TestBrimVisualTroubleshooting:
    """
    Test suite for SAP BRIM Visual Step-by-Step Troubleshooting:
    1. Query activation rules (activates only for BRIM issues/screenshots; normal Q&A untouched).
    2. Troubleshooting state extraction (Turn 1, Turn N, Resolution detection).
    3. SVG validity, title bar format, callouts, rings, and disclaimers.
    4. Single-step prompt enforcement (never list all steps up front, 3-line ticket summary).
    5. Answer planner & adaptive format section integration.
    """

    def test_query_activation_rules(self):
        # 1. BRIM issue descriptions -> MUST trigger
        assert brim_troubleshooting_service.is_brim_troubleshooting_query(
            "Billable items are stuck in status 2 with error in FKKBIX_BIT_DISPLAY"
        ) is True
        assert brim_troubleshooting_service.is_brim_troubleshooting_query(
            "Invoicing run FKINV_M failed with clarification lock"
        ) is True
        assert brim_troubleshooting_service.is_brim_troubleshooting_query(
            "Why did the billing document fail to post to FI-CA contract account?"
        ) is True

        # 2. Screenshots with error context -> MUST trigger
        assert brim_troubleshooting_service.is_brim_troubleshooting_query(
            "Look at this screenshot, what is wrong?",
            has_attachment=True
        ) is True
        assert brim_troubleshooting_service.is_brim_troubleshooting_query(
            "Here is the error",
            attachments_data=[{"file_type": "image", "vision_metadata": {"is_sap": True, "error_text": "Error in FKKBIX"}}]
        ) is True

        # 3. Active multi-turn troubleshooting session -> MUST continue
        chat_context = "Assistant: Step 1 · FKKBIX_BIT_DISPLAY · Display Billable Items\nPlease check status."
        assert brim_troubleshooting_service.is_brim_troubleshooting_query(
            "I checked it and the BIT status is 2",
            chat_history_context=chat_context
        ) is True

        # 4. General SAP Q&A -> MUST NOT trigger (remains normal Q&A)
        assert brim_troubleshooting_service.is_brim_troubleshooting_query(
            "What is SAP SOM?"
        ) is False
        assert brim_troubleshooting_service.is_brim_troubleshooting_query(
            "Explain CI architecture and billing document tables"
        ) is False
        assert brim_troubleshooting_service.is_brim_troubleshooting_query(
            "Define Billable Item Class in Convergent Invoicing"
        ) is False

        # 5. Non-SAP questions -> MUST NOT trigger
        assert brim_troubleshooting_service.is_brim_troubleshooting_query(
            "How do I cook pasta?"
        ) is False

    def test_troubleshooting_state_extraction_and_step_progression(self):
        # Turn 1: Fresh issue
        state_t1 = brim_troubleshooting_service.extract_brim_troubleshooting_state(
            query="Billable items failed to bill in FKKBIX_BILL_M",
            chat_history_context=""
        )
        assert state_t1["is_first_step"] is True
        assert state_t1["current_step_num"] == 1
        assert state_t1["last_step"] == 0
        assert state_t1["is_resolved"] is False
        assert state_t1["affected_stage"] == "billing_document"

        # Turn 2: Following Step 1
        hist_step1 = (
            "User: Billing failed in FKKBIX_BILL_M\n"
            "Assistant: Step 1 · FKKBIX_BIT_DISPLAY · Display Billable Items\n"
            "Please check the BIT status."
        )
        state_t2 = brim_troubleshooting_service.extract_brim_troubleshooting_state(
            query="Status shows 2 - Clarification",
            chat_history_context=hist_step1
        )
        assert state_t2["is_first_step"] is False
        assert state_t2["current_step_num"] == 2
        assert state_t2["last_step"] == 1
        assert state_t2["is_resolved"] is False

        # Turn 3: Following Step 2
        hist_step2 = hist_step1 + "\nUser: Status shows 2\nAssistant: Step 2 · FKKBIX_BIT_CONF · Release BITs"
        state_t3 = brim_troubleshooting_service.extract_brim_troubleshooting_state(
            query="BITs released, now what?",
            chat_history_context=hist_step2
        )
        assert state_t3["current_step_num"] == 3
        assert state_t3["last_step"] == 2
        assert state_t3["is_resolved"] is False

        # Resolution Turn: User confirms fix
        state_res = brim_troubleshooting_service.extract_brim_troubleshooting_state(
            query="It worked! The billing document generated successfully and error is gone.",
            chat_history_context=hist_step2
        )
        assert state_res["is_resolved"] is True

    def test_sap_gui_svg_builder_validity_and_contract(self):
        # Step mockup SVG
        svg_step1 = sap_gui_svg_builder.build_sap_gui_screen_svg(
            step_num=1,
            tcode="FKKBIX_BIT_DISPLAY",
            screen_name="Display Billable Items",
            fields=[
                ("Contract Account", "10029482 (Example)"),
                ("BIT Status", "2 - Clarification (Example)"),
            ],
            highlight_field="BIT Status",
            callouts=[(1, "Check BIT Status field")],
            is_verification=False,
            status="error"
        )

        assert svg_step1.startswith("<svg")
        assert svg_step1.endswith("</svg>")
        # Title bar format: "Step N · <transaction code> · <screen name>"
        assert "Step 1 · FKKBIX_BIT_DISPLAY · Display Billable Items" in svg_step1
        # Numbered callout
        assert "Check BIT Status field" in svg_step1
        # Ring / highlight
        assert 'stroke-dasharray="4,2"' in svg_step1
        # Illustrative mockup disclaimer
        assert "Illustrative mockup · Not an actual system screenshot" in svg_step1

        # XML validity check
        root = ET.fromstring(svg_step1)
        assert root.tag.endswith("svg")

        # Verification mockup SVG
        svg_verif = sap_gui_svg_builder.build_sap_gui_screen_svg(
            step_num="Verification",
            tcode="FKKBIX_BIT_DISPLAY",
            screen_name="Display Billable Items",
            fields=[("BIT Status", "4 - Billed (Example)")],
            highlight_field="BIT Status",
            callouts=[(1, "Verified BIT status is now 4 (Billed)")],
            is_verification=True,
            status="success"
        )
        assert "Verification · FKKBIX_BIT_DISPLAY · Display Billable Items" in svg_verif
        assert "#10B981" in svg_verif  # Success green
        ET.fromstring(svg_verif)

    def test_brim_flow_overview_svg(self):
        overview_svg = sap_gui_svg_builder.build_brim_flow_overview_svg(affected_stage="billing_document")
        assert overview_svg.startswith("<svg")
        assert overview_svg.endswith("</svg>")
        # Stage names
        assert "1. Billable Item (BIT)" in overview_svg
        assert "2. Billing Document" in overview_svg
        assert "3. Invoicing Document" in overview_svg
        assert "4. FI-CA Invoice / Post" in overview_svg
        # Colors: red for affected, green for prior, gray for pending
        assert "AFFECTED (ISSUE)" in overview_svg
        assert "COMPLETED" in overview_svg
        assert "PENDING" in overview_svg
        # XML validity
        ET.fromstring(overview_svg)

    def test_prompt_instructions_single_step_enforcement(self):
        # Turn 1
        inst_t1 = brim_troubleshooting_service.get_troubleshooting_system_instructions(
            state={"current_step_num": 1, "is_first_step": True, "is_resolved": False, "affected_stage": "billing_document"}
        )
        assert "TURN 1 - STEP 1 ONLY" in inst_t1
        assert "ONE-LINE DIAGNOSIS" in inst_t1
        assert "OVERVIEW IMAGE" in inst_t1
        assert "STEP 1 ONLY" in inst_t1
        assert "NEVER list all the steps up front!" in inst_t1
        assert "Step 1 · <transaction code> · <screen name>" in inst_t1

        # Turn 2 (Follow-up)
        inst_t2 = brim_troubleshooting_service.get_troubleshooting_system_instructions(
            state={"current_step_num": 2, "is_first_step": False, "is_resolved": False}
        )
        assert "TURN FOR STEP 2 ONLY" in inst_t2
        assert "GIVE ONLY STEP 2" in inst_t2
        assert "Do NOT list future steps!" in inst_t2
        assert "Step 2 · <transaction code> · <screen name>" in inst_t2

        # Resolution Turn
        inst_res = brim_troubleshooting_service.get_troubleshooting_system_instructions(
            state={"current_step_num": 3, "is_first_step": False, "is_resolved": True}
        )
        assert "RESOLUTION TURN" in inst_res
        assert "Verification · <transaction code> · <screen name>" in inst_res
        assert "Root cause:" in inst_res
        assert "Resolution:" in inst_res
        assert "Verification:" in inst_res

    def test_answer_planner_and_llm_service_integration(self):
        # Answer planner plans BRIM visual troubleshooting archetype
        plan = answer_planner.plan_answer("Billable items locked in FKKBIX_BIT_DISPLAY")
        assert plan["question_type"] == "brim_visual_troubleshooting"

        # Format hint detection
        hint = answer_planner.detect_format_hint(
            query="Billable items locked in FKKBIX_BIT_DISPLAY",
            chat_history_context=""
        )
        assert hint["is_brim_troubleshooting"] is True
        assert hint["brim_troubleshooting_state"]["is_first_step"] is True
        assert hint["brim_troubleshooting_state"]["current_step_num"] == 1

        # LLM adaptive format section builds without error
        fmt, struct, target = llm_service._build_adaptive_format_section(
            query="Billable items locked in FKKBIX_BIT_DISPLAY",
            plan=plan,
            chat_history_context=""
        )
        assert target == 350
        assert "STEP 1 ONLY" in fmt
