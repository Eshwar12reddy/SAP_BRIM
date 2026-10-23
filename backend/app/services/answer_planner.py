import re
from typing import Dict, Any, List, Optional

class AnswerPlanner:
    """
    Question-Aware Answer Planning Service for SAP BRIM Knowledge Assistant.
    
    Identifies the technical inquiry type and dictates evidence-grounded structural guidelines:
    1. Conceptual questions (definition, purpose, role in BRIM, relationships, examples, limitations)
    2. Configuration questions (prerequisites, verified SPRO path, documented steps, validation)
    3. T-code and table lookups (exact identifier, usage, key fields, prerequisites)
    4. Troubleshooting questions (symptom, root causes, diagnostic checks, resolution, validation)
    5. Integration & process-flow questions (components, sequence, exchanged objects e.g. BITs/CITs, failure points)
    6. Comparison questions (direct answer, comparison table, differences/similarities, implications)
    7. Scenario-based technical questions (practical solution, architectural impact)
    8. Follow-up questions (resolved conversational reference, focused direct answer)
    9. Version-specific questions (ECC vs S/4HANA release differences)
    10. Insufficient evidence (explicit boundary, verified vs missing)
    """

    @staticmethod
    def classify_task(query: str, has_attachment: bool = False) -> str:
        """
        Classifies the incoming SAP task into one of five standardized archetypes:
        'architecture', 'screenshot_analysis', 'troubleshooting', 'implementation', or 'explanation'.
        """
        q_lower = query.lower()
        if has_attachment or any(k in q_lower for k in ["screenshot", "screen shot", "attached image", "photo", "what i see", "what do i do next with this image"]):
            return "screenshot_analysis"

        if any(k in q_lower for k in [
            "architecture", "system design", "component diagram", "sequence diagram",
            "data flow diagram", "landscape diagram", "integration architecture",
            "draw", "diagram", "mermaid", "layer", "layers", "end to end brim flow",
            "workflow", "data flow", "flow chart", "flowchart", "visualize", "integration diagram"
        ]) or bool(re.search(r"\b(draw (an? )?.*architecture|draw.*diagram|generate.*diagram|visualize.*flow)\b", q_lower)):
            return "architecture"

        if any(k in q_lower for k in [
            "error", "dump", "st22", "fail", "failed", "dump", "troubleshoot", "issue",
            "stuck", "exception", "locked", "terminate", "connection refused", "bug", "fix error"
        ]):
            return "troubleshooting"

        if any(k in q_lower for k in [
            "how to configure", "configuration steps", "customizing", "spro", "maintain table",
            "setup guide", "configure", "implement", "cutover", "migration cockpit", "ltmc"
        ]):
            return "implementation"

        return "explanation"

    @staticmethod
    def plan_answer(query: str, is_follow_up: bool = False, has_attachment: bool = False, chat_history_context: str = "") -> Dict[str, Any]:
        q_lower = query.lower()

        # 0. Specialized SAP BRIM Visual Step-by-Step Troubleshooting
        try:
            from backend.app.services.brim_troubleshooting_service import brim_troubleshooting_service
            if brim_troubleshooting_service.is_brim_troubleshooting_query(query, chat_history_context=chat_history_context, has_attachment=has_attachment):
                return {
                    "question_type": "brim_visual_troubleshooting",
                    "title": "SAP BRIM Visual Step-by-Step Troubleshooting",
                    "instructions": (
                        "SAP BRIM VISUAL STEP-BY-STEP TROUBLESHOOTING:\n"
                        "Provide a visual consultant response guiding the user ONE STEP AT A TIME:\n"
                        "1. Turn 1: 1-line diagnosis + overview image of BRIM flow + ONLY Step 1 with its simplified SAP GUI mockup image -> wait.\n"
                        "2. Subsequent turns: Interpret user results + ONLY next step with simplified SAP GUI mockup image -> wait.\n"
                        "3. Resolution: Verification mockup image + exact 3-line ticket summary (Root cause:, Resolution:, Verification:).\n"
                        "4. All images returned as valid SVG code blocks (```svg)."
                    )
                }
        except Exception:
            pass

        # 0. Screenshot / Image Analysis
        if has_attachment or any(k in q_lower for k in ["screenshot", "screen shot", "attached image", "attached document", "what do i do next"]):
            return {
                "question_type": "screenshot_analysis",
                "title": "SAP Screenshot & Image Understanding",
                "instructions": (
                    "MANDATORY RESPONSE FORMAT FOR SCREENSHOTS & IMAGES:\n"
                    "Provide the answer strictly using these structured sections:\n\n"
                    "### A. What I see\n"
                    "State the exact page, system, screen, transaction code, error dialog, form, or diagram shown.\n\n"
                    "### B. What the problem is\n"
                    "- **Confirmed observations**: Exactly what is visible on the screen.\n"
                    "- **Likely issue**: Technical root cause clearly separated from unverified assumptions.\n\n"
                    "### C. Your next step\n"
                    "Numbered, beginner-friendly actions:\n"
                    "1. Name the exact visible field, button, or menu item to click or command to run.\n"
                    "2. State the precise value or parameter needed.\n"
                    "3. State what should happen next.\n"
                    "4. What specific information to share or check if the problem continues.\n\n"
                    "### D. Expected result\n"
                    "How the user can confirm the step worked.\n\n"
                    "### E. If the issue continues\n"
                    "The next troubleshooting step for the likely failure mode.\n\n"
                    "SECURITY NOTICE: If any password, OTP, token, or secret is visible in the screenshot, "
                    "never repeat or guess secrets. Issue an immediate caution alert to redact and rotate it!"
                )
            }

        # 0. Architecture & System Design Request
        if any(k in q_lower for k in [
            "architecture", "system design", "component diagram", "sequence diagram",
            "data flow diagram", "landscape diagram", "integration architecture",
            "draw architecture", "show architecture", "brim architecture", "generate diagram",
            "mermaid", "visual diagram", "show workflow", "integration diagram",
            "visualize the data flow", "data flow"
        ]) or bool(re.search(r"\b(draw (an? )?.*architecture|draw.*diagram|generate.*diagram|visualize.*flow)\b", q_lower)):
            return {
                "question_type": "architecture",
                "title": "SAP Enterprise Architecture & System Design",
                "instructions": (
                    "STRUCTURE REQUIREMENT (SAP Enterprise Architecture & Diagram Generation):\n"
                    "1. Executive Architecture Summary: High-level purpose and core business domain.\n"
                    "2. Logical Component Layers (Engagement, Order/Contract Management, Rating/Mediation, Invoicing, Subledger, G/L).\n"
                    "3. Interactive Rendered Mermaid Diagram:\n"
                    "   Provide a valid, complete diagram. Put ```mermaid alone on its own line, then the diagram, then ``` alone on its own line followed by a blank line, and never put any note or remark on a fence line. Adhere strictly to:\n"
                    "   - Output only a valid Mermaid code block, nothing else inside it.\n"
                    "   - Use ASCII characters only (plain hyphen \"-\", straight quotes). Never use U+2011, en/em dashes, or smart quotes.\n"
                    "   - Node IDs must be simple (A, B, C or step1, step2), with no spaces or special characters.\n"
                    "   - Wrap EVERY node label in double quotes: A[\"Label text\"].\n"
                    "   - Use <br/> for line breaks inside labels. Never put a real newline inside a label.\n"
                    "   - Never use double quotes inside a label. Use single quotes instead.\n"
                    "   - Every `subgraph` must have a matching `end`.\n"
                    "   - Keep diagrams under about 25 nodes. Finish the whole diagram.\n"
                    "   - Mermaid syntax: wrap every edge label and node label in double quotes, e.g. A -->|\"Create order (sync)\"| B and A[\"SAP SOM (Order Mgmt)\"]. Use <br/> for line breaks inside quotes. Never use unquoted parentheses, brackets or braces in labels.\n"
                    "   - Grouping systems into logical layers (`subgraph`) with clear component boundaries.\n"
                    "   - Labeled directional arrows with business data exchanged (e.g. Provider Contracts, CITs, BITs, Invoicing Docs).\n"
                    "   - Arrow style shows evidence, not interface type: use a solid arrow (-->) only when a retrieved source explicitly states that flow, and a dashed arrow (-.->) for everything else (general SAP knowledge, assumptions, optional components). Show the interface type in the edge label text (for example -->|\"Sync REST\"|), never with ==>. Keep labels short with no page numbers or document names, and after the diagram list the source document and page for each solid arrow under the heading Diagram sources and evidence.\n"
                    "   - Showing critical dependencies and master-data ownership (BP, CA, Subscription Product, Charge Plan).\n"
                    "   - Showing authentication/security boundaries (mTLS, OAuth2, API Gateway) and error handling, queue monitoring, and reconciliation interfaces.\n"
                    "4. Master Data Ownership and End-to-End Processing Flow.\n"
                    "5. Assumptions and Standard SAP vs Custom Extensions.\n"
                    "6. Documented Best Practices and Citations."
                )
            }

        # 1. Comparison questions
        if any(term in q_lower for term in ["difference between", "compare", "versus", " vs ", "diff between", "comparison"]):
            return {
                "question_type": "comparison",
                "title": "Comparison Analysis",
                "instructions": (
                    "STRUCTURE REQUIREMENT (Comparison):\n"
                    "1. Direct Summary Answer stating the primary distinction.\n"
                    "2. Markdown Comparison Table contrasting key dimensions (Scope, Core Objects, Integration, Processing Mode).\n"
                    "3. Detailed Differences & Similarities based strictly on retrieved documentation.\n"
                    "4. Practical Architectural Implications in SAP BRIM.\n"
                    "5. Citing supporting documents."
                )
            }

        # 2. Troubleshooting questions
        if any(term in q_lower for term in ["error", "fail", "failed", "dump", "troubleshoot", "issue", "stuck", "exception", "cannot", "fix", "lock", "locked", "terminate", "terminated", "abort"]):
            return {
                "question_type": "troubleshooting",
                "title": "Troubleshooting & Diagnostics",
                "instructions": (
                    "STRUCTURE REQUIREMENT (SAP Scenario & Troubleshooting):\n"
                    "Provide a thorough, step-by-step technical solution covering these key areas:\n"
                    "Use explicit diagnostic status labels throughout: **Verified fact**, **Likely hypothesis**, **Evidence required**, **Root cause confirmed** (only when proven by observable evidence), and **Unresolved**.\n"
                    "### 1. Problem Analysis & Business Impact\n"
                    "Understand the problem context, failure symptoms, and end-to-end impact across affected SAP modules without manufacturing unstated amounts or dates.\n"
                    "### 2. Possible Root Causes\n"
                    "List competing hypotheses (prioritized) and clearly explain what evidence supports or disproves each.\n"
                    "### 3. Step-by-Step Troubleshooting (Correct Chronological Order)\n"
                    "Ordered, practical diagnostic steps with exact transaction codes and navigation paths.\n"
                    "### 4. Relevant SAP Documents, Application Logs, Statuses & Interfaces\n"
                    "Detail which logs (SLG1, SM21, SM37), RFC queues (SMQ1/SMQ2/SM58), tables (DFKKOP, DFKKKO, DFKKBIXBIT*), and financial records to inspect.\n"
                    "### 5. Component Isolation (First Failing Component)\n"
                    "Explain how to isolate whether the failure began in SOM, CC, CI, FI-CA, or GL integration.\n"
                    "### 6. Recommended Fixes & Safe Corrective Actions\n"
                    "Actionable, safe recovery steps (reversal, clearing release, re-rating, re-billing) and permanent configuration fixes. NEVER recommend direct database updates or blind retries.\n"
                    "### 7. Validation & Prevention Steps\n"
                    "Explain how to validate the fix (simulation runs, balance reconciliation) and prevent recurrence.\n"
                    "### 8. Relevant Citations & Technical References\n"
                    "Working links or documentation references supporting the technical claims."
                )
            }

        # 3. Scenario-based questions
        if any(term in q_lower for term in [
            "scenario", "end to end", "end-to-end", "business process", "how to handle",
            "how would you", "mid-cycle", "what happens when", "clearing", "dunning",
            "reversal", "reversals", "reconciliation", "billing run", "invoicing run"
        ]):
            return {
                "question_type": "scenario",
                "title": "SAP BRIM Scenario-Based Solution",
                "instructions": (
                    "STRUCTURE REQUIREMENT (SAP Scenario & Troubleshooting):\n"
                    "Provide a thorough, step-by-step technical solution covering these key areas:\n"
                    "Use explicit diagnostic status labels throughout: **Verified fact**, **Likely hypothesis**, **Evidence required**, **Root cause confirmed** (only when proven by observable evidence), and **Unresolved**.\n"
                    "### 1. Problem Analysis & Business Impact\n"
                    "Understand the business context, failure symptoms, and end-to-end impact across SOM, CC, CI, FI-CA, and GL without manufacturing unstated customer details.\n"
                    "### 2. Possible Root Causes\n"
                    "List competing hypotheses (prioritized) and clearly explain what evidence supports or disproves each.\n"
                    "### 3. Step-by-Step Troubleshooting (Correct Chronological Order)\n"
                    "Ordered, practical diagnostic steps with exact transaction codes and navigation paths.\n"
                    "### 4. Relevant SAP Documents, Application Logs, Statuses & Interfaces\n"
                    "Detail which logs (SLG1, SM21, SM37), RFC queues (SMQ1/SMQ2/SM58), tables (DFKKOP, DFKKKO, DFKKBIXBIT*), and financial records to inspect.\n"
                    "### 5. Component Isolation (First Failing Component)\n"
                    "Explain how to isolate whether the failure originated in SOM, CC, CI, FI-CA, or GL integration.\n"
                    "### 6. Recommended Fixes & Safe Corrective Actions\n"
                    "Actionable, safe recovery steps (reversals, clearing adjustment, re-rating, re-billing) and permanent configuration fixes. NEVER recommend direct database modifications.\n"
                    "### 7. Validation & Prevention Steps\n"
                    "Explain how to validate the fix (simulation runs, balance reconciliation) and prevent recurrence.\n"
                    "### 8. Relevant Citations & Technical References\n"
                    "Working links or documentation references supporting the technical claims."
                )
            }

        # 4. Configuration questions
        if any(term in q_lower for term in ["how to configure", "configuration steps", "customizing", "spro", "maintain table", "setup guide", "configure"]):
            return {
                "question_type": "configuration",
                "title": "Configuration Guide",
                "instructions": (
                    "STRUCTURE REQUIREMENT (Configuration):\n"
                    "1. Objective: What component or process is being configured.\n"
                    "2. Prerequisites and master data dependencies.\n"
                    "3. Exact SPRO / IMG Configuration Path (ONLY if verified in evidence; never invent paths).\n"
                    "4. Step-by-Step Documented Configuration Sequence.\n"
                    "5. Expected System Behavior & Validation Checks."
                )
            }

        # 5. T-Code & Table Lookup questions
        if (
            re.search(r"\b(tcode|t-code|transaction|table|se16|se11|sm30)\b", q_lower)
            or re.search(r"\b(/[a-z0-9_]{2,}/[a-z0-9_]+|[a-z]{1,2}[0-9]{2}[a-z0-9]?)\b", q_lower)
            or re.search(r"\b(dfkk[a-z0-9_]+|fkk[a-z0-9_]+|erdk|erch)\b", q_lower)
        ):
            return {
                "question_type": "tcode_table",
                "title": "Technical Identifier Lookup",
                "instructions": (
                    "STRUCTURE REQUIREMENT (Technical Identifier / T-Code / Table Lookup):\n"
                    "1. Identifier Name & Documented Purpose.\n"
                    "2. Functional Context within SAP BRIM (e.g. CI Billable Item processing, FI-CA clearing, SOM order).\n"
                    "3. Documented Key Fields, Selection Parameters, or Menu Access.\n"
                    "4. Execution Prerequisites and Related Transactions.\n"
                    "CRITICAL: Do NOT invent transaction codes or table names not present in the evidence."
                )
            }

        # 6. Integration and Process-Flow questions
        if any(term in q_lower for term in ["process flow", "end to end", "integration", "how does it interact", "flow from", "billing cycle", "order to cash"]):
            return {
                "question_type": "integration",
                "title": "Process Flow & Integration",
                "instructions": (
                    "STRUCTURE REQUIREMENT (Integration & End-to-End Flow):\n"
                    "1. Involved SAP BRIM Architecture Components (e.g. SOM, CC, CI, FI-CA).\n"
                    "2. End-to-End Processing Sequence (ordered numbered steps).\n"
                    "3. Information & Objects Exchanged (e.g. Provider Order -> Subscription Contract -> CIT -> BIT -> Invoicing Document -> FI-CA Open Item).\n"
                    "4. Component Handshakes and Dependencies.\n"
                    "5. Documented Failure Points & Reconciliation Considerations."
                )
            }

        # 7. Version-specific questions
        if any(term in q_lower for term in ["s/4hana", "s4hana", "ecc", "release", "version", "upgrade", "clean core"]):
            return {
                "question_type": "version_specific",
                "title": "Release & Version Specifics",
                "instructions": (
                    "STRUCTURE REQUIREMENT (Version & Release Specifics):\n"
                    "1. Release Context (S/4HANA vs ECC / Classical BRIM).\n"
                    "2. Documented Functional or Architectural Differences.\n"
                    "3. Migration or Modernization Considerations supported by the evidence.\n"
                    "4. Explicitly state if certain features are restricted to specific releases."
                )
            }

        # 7. Follow-up conversational question
        if is_follow_up:
            return {
                "question_type": "followup",
                "title": "Conversational Follow-up",
                "instructions": (
                    "STRUCTURE REQUIREMENT (Follow-up Response):\n"
                    "1. Direct, concise answer addressing the specific follow-up inquiry immediately.\n"
                    "2. Seamlessly link to the established conversation context without repeating lengthy introductions.\n"
                    "3. Preserve exact technical identifiers discussed in prior turns.\n"
                    "4. Cite supporting passages."
                )
            }

        # 8. Conceptual / Overview question (Default)
        return {
            "question_type": "conceptual",
            "title": "Conceptual Architecture & Overview",
            "instructions": (
                "STRUCTURE REQUIREMENT (Conceptual Architecture):\n"
                "1. Direct Definition & Purpose.\n"
                "2. Functional Mechanism: How the component operates.\n"
                "3. Place in the SAP BRIM Landscape and relationships with adjacent components.\n"
                "4. Practical Example or Business Use Case (where supported by evidence).\n"
                "5. Important Constraints, Best Practices, and Documented Considerations."
            )
        }

    @staticmethod
    def extract_guided_troubleshooting_state(
        query: str = "",
        chat_history_context: str = "",
        has_attachment: bool = False,
        chat_history: Optional[List[Dict[str, Any]]] = None,
        current_query: str = "",
    ) -> Dict[str, Any]:
        """
        Extracts and tracks lightweight session state for screenshot-guided troubleshooting.
        Tracks:
        - is_active: whether this query is part of a guided troubleshooting session
        - is_first_step: True if this is the initial screenshot turn
        - current_step_num: next step number to prescribe (1, 2, 3...)
        - last_step: highest step completed so far
        - is_resolved: True if user reports problem is fixed/working
        - wants_full_list: True if user explicitly asks for all steps at once
        """
        active_query = current_query or query or ""
        q_lower = active_query.lower().strip()

        if chat_history and not chat_history_context:
            chat_history_context = "\n".join(
                f"{m.get('role', '')}: {m.get('content', '')}" for m in chat_history if isinstance(m, dict)
            )

        hist_text = chat_history_context.lower() if chat_history_context else ""

        # Check if user says issue is resolved/working
        resolved_patterns = [
            r"\b(it worked|issue resolved|problem resolved|fixed|all good now|it's fixed|its fixed|working fine now|solved|it cleared the error|error is gone|now it works|issue is fixed)\b"
        ]
        is_resolved = any(re.search(pat, q_lower) for pat in resolved_patterns)

        # Check if user requests the full list of steps at once
        full_list_patterns = [
            r"\b(all (the )?steps|full list|all steps|complete list|every step|list all steps|show all steps|give me all steps)\b"
        ]
        wants_full_list = any(re.search(pat, q_lower) for pat in full_list_patterns)

        # Scan previous context for highest step number
        steps_found = []
        if hist_text:
            matches = re.findall(r"(?:step|turn)\s*(\d+)", hist_text, re.IGNORECASE)
            for m in matches:
                try:
                    steps_found.append(int(m))
                except ValueError:
                    pass

        last_step = max(steps_found) if steps_found else 0
        has_prior_troubleshooting = last_step > 0 or "what the screenshot shows" in hist_text or "screenshot" in hist_text

        is_first_turn_image = has_attachment and (last_step == 0)
        is_active = is_first_turn_image or has_prior_troubleshooting or (has_attachment and last_step > 0)
        next_step_num = 1 if is_first_turn_image else (last_step + 1 if last_step > 0 else 1)

        return {
            "is_active": is_active,
            "is_first_step": is_first_turn_image or (next_step_num == 1),
            "current_step_num": next_step_num,
            "last_step": last_step,
            "is_resolved": is_resolved,
            "wants_full_list": wants_full_list,
        }

    @staticmethod
    def detect_format_hint(
        query: str = "",
        chat_history_context: str = "",
        memory_context: str = "",
        has_attachment: bool = False,
        chat_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Lightweight hint detector for ChatGPT-style adaptive answers.
        Identifies format requests (steps, diagrams, tables, short answer, no diagram),
        guided-step troubleshooting state, and conversational continuity hints.
        
        CRITICAL: Never raises an exception; gracefully returns defaults on any error.
        """
        if chat_history and not chat_history_context:
            chat_history_context = "\n".join(
                f"{m.get('role', '')}: {m.get('content', '')}" for m in chat_history if isinstance(m, dict)
            )
        try:
            q_clean = query.strip()
            q_lower = q_clean.lower()
            
            # Explicit single-turn format requests
            wants_no_diagram = bool(re.search(
                r"\b(no diagram|without diagram|don'?t draw|no charts?|no flowchart)\b",
                q_lower
            ))

            is_sequence = bool(re.search(r"\b(sequence diagram|sequence flow|call sequence)\b", q_lower))
            if is_sequence:
                diagram_type = "sequenceDiagram"
            elif bool(re.search(r"\b(horizontal|left to right|flowchart lr|lr)\b", q_lower)):
                diagram_type = "flowchart LR"
            else:
                diagram_type = "flowchart TD"

            wants_diagram = not wants_no_diagram and bool(
                re.search(
                    r"\b(draw (an? )?.*architecture|draw (the )?(flow|diagram|architecture|workflow)|draw architecture|generate (a )?diagram|show (the )?workflow|show (the )?flow|show flow|give (me )?(the )?structure|draw it|how do the components connect|end-to-end process|diagram|flowchart|flow chart|process flow|architecture diagram|flow diagram|sequence diagram|integration diagram|visualize( the)?( data)? flow|visualize)\b",
                    q_lower
                ) or (
                    ("flow" in q_lower or "structure" in q_lower or "diagram" in q_lower or "architecture" in q_lower or "workflow" in q_lower)
                    and any(v in q_lower for v in ["show", "give", "draw", "display", "provide", "generate", "visualize", "create", "render"])
                )
            )
            
            wants_steps = bool(re.search(
                r"\b(step[- ]by[- ]step|troubleshooting steps|give steps|give me steps|in steps|in points|what should i check|guide me|how do i (fix|configure|set up|run|resolve|troubleshoot|check))\b",
                q_lower
            ))
            
            wants_short = bool(re.search(
                r"\b(short answer|concise|briefly|in short|one line|one sentence|quick answer)\b",
                q_lower
            ))
            
            wants_table = bool(re.search(
                r"\b(table please|as a table|in a table|tabular|give (me )?a table|compact table)\b",
                q_lower
            ))
            
            wants_points = bool(re.search(
                r"\b(only points|in points|bullet points|in bullets|bulleted)\b",
                q_lower
            ))

            wants_detail = bool(re.search(
                r"\b(explain in detail|detailed explanation|in depth|elaborate)\b",
                q_lower
            ))
            
            # Follow-up continuity: e.g. "what is the next step?", "continue", "what next?"
            is_followup_next_step = bool(re.search(
                r"\b(what is the next step|what('s| is) next|next step|continue|what about fi-ca|what about som|what about cc|what about ci)\b",
                q_lower
            ))
            
            followup_instructions = ""
            if is_followup_next_step and chat_history_context:
                matches = re.findall(r"(?:Step|STEP)\s*(\d+)|(?:\n|^)\s*(\d+)\.\s+", chat_history_context)
                step_numbers = []
                for m1, m2 in matches:
                    val = m1 or m2
                    if val and val.isdigit():
                        step_numbers.append(int(val))
                if step_numbers:
                    highest_step = max(step_numbers)
                    next_step = highest_step + 1
                    followup_instructions = (
                        f"The user is continuing from an earlier step-by-step sequence where Step {highest_step} was reached. "
                        f"Continue numbering naturally starting at Step {next_step}. "
                        f"Do not restart from Step 1 and do not repeat previous summaries. Maintain the established style."
                    )
                else:
                    followup_instructions = (
                        "The user is continuing the prior conversation. "
                        "Continue naturally without repeating previous summaries or restarting."
                    )
            
            # Standing preferences in memory_context (user-scoped)
            standing_pref = ""
            if memory_context:
                mem_lower = memory_context.lower()
                if "no diagram" in mem_lower or "without diagram" in mem_lower:
                    standing_pref = "no diagram"
                    wants_no_diagram = True
                    wants_diagram = False
                elif "short answer" in mem_lower or "concise" in mem_lower:
                    standing_pref = "short answer"
                    wants_short = True
                elif "only points" in mem_lower or "bullet points" in mem_lower:
                    standing_pref = "only points"
                    wants_points = True
                elif "table" in mem_lower:
                    standing_pref = "table"
                    wants_table = True
            
            # Simple definition or conceptual question
            is_simple_question = (
                len(q_clean) < 100
                and bool(re.search(r"^(what is|what are|define|why does|what does|meaning of)\b", q_lower))
                and not wants_steps
                and not wants_diagram
                and not wants_table
            )

            # Screenshot Guided-Step Troubleshooting tracking
            troubleshooting_state = AnswerPlanner.extract_guided_troubleshooting_state(
                query=query,
                chat_history_context=chat_history_context,
                has_attachment=has_attachment
            )
            is_guided_step = troubleshooting_state["is_active"]

            # SAP BRIM Visual Step-by-Step Troubleshooting tracking
            from backend.app.services.brim_troubleshooting_service import brim_troubleshooting_service
            is_brim_troubleshooting = brim_troubleshooting_service.is_brim_troubleshooting_query(
                query=query,
                chat_history=chat_history,
                chat_history_context=chat_history_context,
                has_attachment=has_attachment
            )
            brim_troubleshooting_state = {}
            if is_brim_troubleshooting:
                brim_troubleshooting_state = brim_troubleshooting_service.extract_brim_troubleshooting_state(
                    query=query,
                    chat_history=chat_history,
                    chat_history_context=chat_history_context,
                    has_attachment=has_attachment
                )
            
            return {
                "wants_steps": wants_steps,
                "wants_diagram": wants_diagram,
                "diagram_type": diagram_type if wants_diagram else None,
                "wants_no_diagram": wants_no_diagram,
                "wants_short": wants_short,
                "wants_table": wants_table,
                "wants_points": wants_points,
                "wants_detail": wants_detail,
                "is_followup_next_step": is_followup_next_step,
                "followup_instructions": followup_instructions,
                "standing_preference": standing_pref,
                "is_simple_question": is_simple_question,
                "is_guided_step": is_guided_step,
                "troubleshooting_state": troubleshooting_state,
                "is_brim_troubleshooting": is_brim_troubleshooting,
                "brim_troubleshooting_state": brim_troubleshooting_state,
            }
        except Exception:
            # Never fail a request on hint error
            return {
                "wants_steps": False,
                "wants_diagram": False,
                "diagram_type": None,
                "wants_no_diagram": False,
                "wants_short": False,
                "wants_table": False,
                "wants_points": False,
                "wants_detail": False,
                "is_followup_next_step": False,
                "followup_instructions": "",
                "standing_preference": "",
                "is_simple_question": False,
                "is_guided_step": False,
                "troubleshooting_state": {"is_active": False, "is_first_step": False, "current_step_num": 1, "last_step": 0, "is_resolved": False, "wants_full_list": False},
                "is_brim_troubleshooting": False,
                "brim_troubleshooting_state": {},
            }


answer_planner = AnswerPlanner()

