import re
from typing import Dict, Any, List, Optional
from backend.app.services.visual.sap_gui_svg_builder import sap_gui_svg_builder


class BrimTroubleshootingService:
    """
    Dedicated service for SAP BRIM Visual Step-by-Step Troubleshooting.

    Enforces the specialized assistant protocol:
    1. Read issue or screenshot -> say in one line what is going wrong.
    2. Turn 1: BRIM flow overview SVG + ONLY Step 1 with its SAP GUI SVG mockup -> stop & wait.
    3. Follow-up turns: Explain user's result -> give ONLY the next step with its SAP GUI SVG mockup -> stop & wait.
    4. Resolution turn: Verification SVG mockup + exact 3-line ticket summary:
       Root cause: ...
       Resolution: ...
       Verification: ...
    5. Accuracy rules: Real SAP t-codes, illustrative mockup watermark, read-only checks first.
    """

    BRIM_KEYWORDS = [
        "brim", "convergent invoicing", "convergent charging", "billable item", "billing document",
        "invoicing document", "dfkkbix", "fkkbix", "fkkinv", "dfkkinv", "ci billing",
        "ci invoice", "ci invoicing", "fica", "fi-ca", "contract account", "bit class",
        "bits", "cits", "consumption item", "provider contract", "fpl9", "fp07", "fp08",
        "billing run", "invoicing run", "clarification worklist", "emma", "fkkbix_bill_m",
        "fkkbix_bill_s", "fkkinv_m", "fkkinv_s", "fkkbix_bit_display", "fkkbix_bit_conf",
        "fkkinv_rev", "fkkbix_bill_rev"
    ]

    TROUBLESHOOTING_KEYWORDS = [
        "error", "fail", "failed", "failure", "dump", "st22", "stuck", "exception",
        "issue", "problem", "locked", "cannot", "can't", "troubleshoot", "why did",
        "not generated", "missing", "rejected", "reversal", "reconciliation", "clarification"
    ]

    @classmethod
    def is_brim_troubleshooting_query(
        cls,
        query: str,
        chat_history: Optional[List[Dict[str, Any]]] = None,
        chat_history_context: str = "",
        has_attachment: bool = False,
        attachments_data: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """
        Determines whether the incoming user query or session represents an SAP BRIM troubleshooting issue.
        Activates ONLY for SAP BRIM issue descriptions or error screenshots.
        Normal SAP Q&A (e.g. 'What is SAP SOM?', 'Explain CI architecture') must return False.
        """
        q_lower = (query or "").lower().strip()

        # 1. Check for error screenshot
        if has_attachment or attachments_data:
            if attachments_data:
                for att in attachments_data:
                    vm = att.get("vision_metadata") or {}
                    if vm.get("is_sap") is True or att.get("file_type") == "image":
                        # If image has an error or is an SAP GUI screenshot
                        if vm.get("error_text") or any(k in str(vm).lower() for k in ["error", "message", "dump", "tcode", "status", "brim", "fica", "fkk"]):
                            return True
            if has_attachment:
                # Any screenshot with error or troubleshooting keywords in user message
                if any(t in q_lower for t in cls.TROUBLESHOOTING_KEYWORDS) or any(b in q_lower for b in cls.BRIM_KEYWORDS):
                    return True
                # If user uploaded a screenshot and asks what to do next
                if any(k in q_lower for k in ["screenshot", "screen shot", "what is wrong", "look at this", "fix this", "error"]):
                    return True

        # 2. Check for active multi-turn troubleshooting in chat history
        hist_text = chat_history_context.lower() if chat_history_context else ""
        if chat_history and not hist_text:
            hist_text = " ".join(str(m.get("content", "")).lower() for m in chat_history if isinstance(m, dict))

        if hist_text:
            if any(marker in hist_text for marker in [
                "step 1 ·", "step 1:", "step 2 ·", "step 2:", "brim flow overview", "what is going wrong", "root cause:"
            ]):
                # If already in an active troubleshooting session, continue unless user starts a completely new non-troubleshooting topic
                if not bool(re.search(r"^(what is|define|who is|tell me about)\s+(?!the error|this error)", q_lower)):
                    return True

        # 3. Check text-based BRIM issue description
        is_brim = any(k in q_lower for k in cls.BRIM_KEYWORDS)
        is_issue = any(t in q_lower for t in cls.TROUBLESHOOTING_KEYWORDS)

        # Must have both BRIM context AND an issue/error description
        if is_brim and is_issue:
            # Exclude purely conceptual questions that just mention the word "error" in a definition context
            if re.search(r"^(what is|define|explain)\b", q_lower) and "how to" not in q_lower and "fix" not in q_lower:
                return False
            return True

        return False

    @classmethod
    def extract_brim_troubleshooting_state(
        cls,
        query: str = "",
        chat_history: Optional[List[Dict[str, Any]]] = None,
        chat_history_context: str = "",
        has_attachment: bool = False,
    ) -> Dict[str, Any]:
        """
        Extracts step number, affected BRIM stage, and resolution status from conversation history.
        """
        q_lower = (query or "").lower().strip()

        hist_text = chat_history_context.lower() if chat_history_context else ""
        if chat_history and not hist_text:
            hist_text = " ".join(str(m.get("content", "")).lower() for m in chat_history if isinstance(m, dict))

        # Check for user resolution confirmation
        resolved_patterns = [
            r"\b(it worked|issue resolved|problem resolved|fixed|all good now|it's fixed|its fixed|working fine now|solved|it cleared the error|error is gone|now it works|issue is fixed|verified)\b"
        ]
        is_resolved = any(re.search(pat, q_lower) for pat in resolved_patterns)

        # Detect highest completed step in history
        steps_found = []
        if hist_text:
            matches = re.findall(r"step\s*(\d+)", hist_text, re.IGNORECASE)
            for m in matches:
                try:
                    steps_found.append(int(m))
                except ValueError:
                    pass

        last_step = max(steps_found) if steps_found else 0
        is_first_step = (last_step == 0)
        current_step_num = 1 if is_first_step else (last_step + 1)

        # Detect affected BRIM stage
        combined_text = f"{hist_text} {q_lower}"
        if any(k in combined_text for k in ["fica", "fpl9", "fp07", "fp08", "clearing", "contract account balance", "dunning"]):
            affected_stage = "invoice"
        elif any(k in combined_text for k in ["fkkinv", "invoicing document", "erdk", "invoicing run", "invoice creation"]):
            affected_stage = "invoicing_document"
        elif any(k in combined_text for k in ["fkkbix_bill", "billing document", "dfkkbix_billdoc", "billing run"]):
            affected_stage = "billing_document"
        else:
            affected_stage = "billable_item"

        return {
            "is_active": True,
            "is_first_step": is_first_step,
            "current_step_num": current_step_num,
            "last_step": last_step,
            "is_resolved": is_resolved,
            "affected_stage": affected_stage,
        }

    @classmethod
    def get_troubleshooting_system_instructions(
        cls,
        state: Dict[str, Any],
        query: str = "",
    ) -> str:
        """
        Builds the strict, specialized system instructions for the SAP BRIM visual step-by-step troubleshooting assistant.
        """
        step_num = state.get("current_step_num", 1)
        is_first = state.get("is_first_step", True)
        is_resolved = state.get("is_resolved", False)
        affected_stage = state.get("affected_stage", "billing_document")

        # 1. Resolution Turn instructions
        if is_resolved:
            return (
                "ROLE & FEATURE: SAP BRIM VISUAL STEP-BY-STEP TROUBLESHOOTING (RESOLUTION TURN)\n"
                "The user reports that the diagnostic/corrective action worked and the issue is resolved!\n\n"
                "YOU MUST STRICTLY FOLLOW THIS EXACT FORMAT:\n"
                "1. Brief congratulatory confirmation (1-2 sentences) confirming the SAP BRIM issue is successfully resolved.\n"
                "2. A verification image rendered as an SVG code block (```svg) showing the screen after the fix:\n"
                "   - Window title bar: \"Verification · <transaction code> · <screen name>\"\n"
                "   - Highlight the successful/cleared status or posted document with a green ring.\n"
                "   - Numbered callout badge (1) stating the verified state.\n"
                "   - Footer note: \"Illustrative mockup · Not an actual system screenshot\".\n"
                "3. Finish with the EXACT 3-line root-cause summary the user can paste into a ticket:\n"
                "Root cause: <specific technical root cause identified>\n"
                "Resolution: <exact action taken in SAP to resolve>\n"
                "Verification: <transaction code and document/status check proving success>\n\n"
                "Do NOT provide further steps."
            )

        # 2. Turn 1 (First Step) instructions
        if is_first:
            return (
                "ROLE & FEATURE: SAP BRIM VISUAL STEP-BY-STEP TROUBLESHOOTING (TURN 1 - STEP 1 ONLY)\n"
                "You are an SAP BRIM (Convergent Invoicing) support consultant who explains every issue visually, ONE STEP AT A TIME.\n\n"
                "YOU MUST STRICTLY FOLLOW THIS EXACT PROTOCOL:\n"
                "1. ONE-LINE DIAGNOSIS: Read the issue or screenshot and state in EXACTLY ONE LINE what is going wrong.\n"
                "2. OVERVIEW IMAGE: Provide an overview SVG code block (```svg) showing where the issue sits in the BRIM flow:\n"
                "   billable item > billing document > invoicing document > invoice\n"
                f"   (Affected stage: '{affected_stage}' highlighted in RED, successful prior stages in GREEN, downstream stages in GRAY).\n"
                "3. STEP 1 ONLY: Provide ONLY Step 1 with its image, then stop and wait. NEVER list all the steps up front!\n"
                "   - Action text: Name the exact real SAP transaction code, navigation path, and read-only diagnostic check to perform.\n"
                "   - Simplified SAP GUI mockup image as an SVG code block (```svg):\n"
                "     * Window title bar: \"Step 1 · <transaction code> · <screen name>\"\n"
                "     * Menu bar and command field showing the transaction code (e.g. /nFKKBIX_BIT_DISPLAY)\n"
                "     * Form or table with realistic sample values (marked with Example)\n"
                "     * Ring (highlight border in red or amber) around the exact target field, row, or button to inspect\n"
                "     * Numbered callout circle (1) with a short instruction beside it (max 8 words!)\n"
                "     * Footer note: \"Illustrative mockup · Not an actual system screenshot\"\n"
                "4. CALL TO ACTION: Ask the user to perform this check in their SAP system and reply with the result or upload a new screenshot.\n\n"
                "ACCURACY & SAFETY RULES:\n"
                "- Use only real SAP transaction codes (e.g. FKKBIX_BIT_DISPLAY, FKKBIX_BILL_M, FKKINV_M, FPL9, SLG1, SM12).\n"
                "- Prefer read-only diagnostic checks first before recommending any postings or reversals.\n"
                "- Mark all sample numbers and error messages as examples.\n"
                "- Do NOT invent fields or transaction codes. Answer only SAP questions."
            )

        # 3. Follow-up Turn (Step 2..N) instructions
        return (
            f"ROLE & FEATURE: SAP BRIM VISUAL STEP-BY-STEP TROUBLESHOOTING (TURN FOR STEP {step_num} ONLY)\n"
            "You are an SAP BRIM support consultant guiding the user ONE STEP AT A TIME.\n\n"
            "YOU MUST STRICTLY FOLLOW THIS EXACT PROTOCOL:\n"
            "1. EXPLAIN THE USER'S RESULT: In 1-2 concise sentences, interpret what the user reported or showed from the previous check.\n"
            f"2. GIVE ONLY STEP {step_num}: Give ONLY Step {step_num} with its image, then STOP and wait. Do NOT list future steps!\n"
            f"   - Action text: State the concrete diagnostic check or safe corrective action for Step {step_num}.\n"
            f"   - Simplified SAP GUI mockup image as an SVG code block (```svg):\n"
            f"     * Window title bar: \"Step {step_num} · <transaction code> · <screen name>\"\n"
            f"     * Menu bar and command field with the transaction code\n"
            f"     * Fields table with realistic sample values (labeled Example)\n"
            f"     * Ring around the exact field, row, or button to act on\n"
            f"     * Numbered callout circles (1, 2) with short instructions beside each (max 8 words!)\n"
            f"     * Red = error, Green = success, Gray = neutral\n"
            f"     * Footer note: \"Illustrative mockup · Not an actual system screenshot\"\n"
            f"3. CALL TO ACTION: Ask the user to perform Step {step_num} and reply with the result or upload a new screenshot.\n\n"
            "ACCURACY & SAFETY RULES:\n"
            "- Use only confirmed, real SAP transaction codes and screen names.\n"
            "- Prefer read-only checks first. Explain risk before recommending reversals or cancellations.\n"
            "- Mark all numbers as examples and screens as illustrative mockups.\n"
            "- Never claim the issue is fixed without evidence from the user."
        )


brim_troubleshooting_service = BrimTroubleshootingService()
