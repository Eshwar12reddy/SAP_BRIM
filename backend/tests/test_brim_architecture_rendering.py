import pytest
import re
from unittest.mock import Mock, patch
from backend.app.services.answer_planner import answer_planner
from backend.app.services.llm_service import llm_service
from backend.app.services.vision_service import vision_service
from backend.app.services.rag_service import rag_service


def test_1_detect_diagram_request_phrases():
    """
    Acceptance Test 1:
    Detect prompts containing phrases such as:
    - "draw architecture"
    - "generate diagram"
    - "show workflow"
    - "sequence diagram"
    - "integration diagram"
    - "visualize the data flow"
    - "Draw an end-to-end SAP BRIM architecture covering SOM, Convergent Charging (CC), Convergent Invoicing (CI), FI-CA, and SAP S/4HANA Finance."
    """
    phrases = [
        "Draw an end-to-end SAP BRIM architecture covering SOM, Convergent Charging (CC), Convergent Invoicing (CI), FI-CA, and SAP S/4HANA Finance.",
        "Please draw architecture for subscription billing",
        "Can you generate diagram of SOM to CC integration?",
        "Show workflow for billable item creation in CI",
        "Give me a sequence diagram of provider contract creation",
        "Provide an integration diagram between CC and CI",
        "Visualize the data flow from mediation into FI-CA",
    ]

    for p in phrases:
        hint = answer_planner.detect_format_hint(p)
        assert hint["wants_diagram"] is True, f"Failed to detect diagram intent in: {p}"
        task_type = answer_planner.classify_task(p)
        assert task_type == "architecture", f"Failed to classify as architecture: {p}"


def test_2_normal_questions_remain_text_without_diagram():
    """
    Acceptance Test 3:
    Preserve normal text responses for questions that do not request diagrams.
    """
    normal_questions = [
        "What is the function of FI-CA in SAP?",
        "How do I configure provider contract replication in SOM?",
        "What is a billable item class in Convergent Invoicing?",
        "Explain the difference between BITs and CITs in SAP BRIM.",
    ]

    for q in normal_questions:
        hint = answer_planner.detect_format_hint(q)
        assert hint["wants_diagram"] is False, f"Normal question falsely flagged as diagram: {q}"


def test_3_generate_brim_architecture_mermaid_structure():
    """
    Acceptance Test 2 & 4:
    Valid Mermaid diagram containing all required SAP BRIM components:
    - Customer Portal / Web Shop
    - API Gateway
    - SAP SOM
    - Subscription / Provider Contract
    - CC
    - Rated Usage / Billable Items
    - CI (Billing & Invoicing)
    - FI-CA (Receivables, Payments, Clearing)
    - S/4HANA Finance General Ledger
    - Optional usage sources & mediation before CC
    - External payment gateways & banks
    """
    query = "Draw an end-to-end SAP BRIM architecture covering SOM, Convergent Charging (CC), Convergent Invoicing (CI), FI-CA, and SAP S/4HANA Finance."
    mermaid = vision_service.generate_brim_architecture_mermaid(query)

    assert "flowchart" in mermaid
    # Required logical components
    assert "Customer Portal / Web Shop" in mermaid
    assert "API Gateway" in mermaid
    assert "SAP Subscription Order Management (SOM)" in mermaid
    assert "Provider Contract" in mermaid
    assert "SAP Convergent Charging (CC)" in mermaid
    assert "Billable Items (BITs)" in mermaid
    assert "SAP Convergent Invoicing: Billing" in mermaid
    assert "SAP Convergent Invoicing: Invoicing" in mermaid
    assert "SAP FI-CA" in mermaid
    assert "SAP S/4HANA Finance General Ledger" in mermaid
    # External integration
    assert "Payment Gateway" in mermaid
    assert "House Banks" in mermaid
    assert "Usage Mediation" in mermaid

    # Validate that all node and edge labels are wrapped in double quotes
    for line in mermaid.splitlines():
        line = line.strip()
        if not line or line.startswith("%%") or line in ("flowchart LR", "flowchart TD", "end"):
            continue
        if "-->|" in line or "-.->|" in line or "==>|" in line:
            # Check edge label has double quotes
            edge_match = re.search(r"\|(.*?)\|", line)
            if edge_match:
                label = edge_match.group(1)
                assert label.startswith('"') and label.endswith('"'), f"Edge label not quoted: {line}"


def test_4_sequence_diagram_detection_and_generation():
    """
    Acceptance Test 2:
    Ask for a sequence diagram. The sequence diagram should render correctly.
    """
    query = "Show sequence diagram for subscription ordering and charging in BRIM"
    hint = answer_planner.detect_format_hint(query)
    assert hint["wants_diagram"] is True
    assert hint["diagram_type"] == "sequenceDiagram"

    diagram = vision_service.generate_diagram(query)
    assert "sequenceDiagram" in diagram
    assert "autonumber" in diagram
    assert "Customer" in diagram
    assert "SAP SOM" in diagram
    assert "SAP CC" in diagram
    assert "SAP CI" in diagram
    assert "SAP FI-CA" in diagram


def test_5_llm_guidance_enforces_mermaid_over_plain_text():
    """
    Ensure _build_adaptive_format_section instructs the model to use ```mermaid
    and explicitly forbids plain text ASCII arrows.
    """
    query = "Draw an end-to-end SAP BRIM architecture covering SOM, CC, CI, FI-CA, and S/4HANA Finance."
    plan = answer_planner.plan_answer(query)
    hint = answer_planner.detect_format_hint(query)

    format_guidance, _, _ = llm_service._build_adaptive_format_section(query, plan=plan)

    assert "```mermaid" in format_guidance
    assert "Mermaid Diagram Syntax Rules" in format_guidance
    assert "Never output ASCII arrows or plain text diagrams" in format_guidance
    assert "USER PORTAL -> SOM -> CC -> CI -> FI-CA -> S/4HANA Finance" in format_guidance


def test_6_stream_query_guarantees_diagram():
    """
    Acceptance Test 1 & 4:
    Even if the LLM output omits a ```mermaid block during streaming,
    the pipeline guarantees a verified Mermaid diagram is yielded in the final response.
    """
    query = "Draw an end-to-end SAP BRIM architecture"
    mock_db = Mock()

    with patch.object(rag_service, "_search_with_kb_fallback") as mock_search, \
         patch.object(llm_service, "stream_answer") as mock_stream:

        mock_search.return_value = (
            {"selected_passages": [{"chunk_id": "1", "document_name": "BRIM Guide", "chunk_text": "SOM to CC"}]},
            [],
            True,
            [],
            {"confidence": 0.88, "evidence_score": 0.88}
        )
        # LLM streams textual explanation without a mermaid codeblock
        mock_stream.return_value = iter([
            "Here is the architectural overview of SAP BRIM: ",
            "SOM handles orders, CC handles charging, CI invoices."
        ])

        chunks = list(rag_service.stream_query(
            db=mock_db,
            query=query,
            chat_history=[],
            user=Mock(id="test-user")
        ))

        # Reconstruct token content
        tokens = [c["content"] for c in chunks if c.get("type") == "token"]
        full_text = "".join(tokens)

        # Mermaid block must have been appended!
        assert "```mermaid" in full_text
        assert "SAP Subscription Order Management (SOM)" in full_text
        assert "SAP Convergent Charging (CC)" in full_text
        assert "SAP Convergent Invoicing" in full_text


def test_7_mermaid_blocks_not_corrupted_by_unverified_flagging():
    """
    Ensure _sanitize_and_verify_identifiers NEVER modifies identifiers inside
    ```mermaid code blocks, preventing errors like:
    'subgraph ORDER_MGMT (unverified, confirm in your system)'
    """
    answer_with_mermaid = (
        "Here is the architecture:\n"
        "```mermaid\n"
        "flowchart TD\n"
        "    subgraph ORDER_MGMT[\"Order Management\"]\n"
        "        SOM[\"SAP SOM\"]\n"
        "    end\n"
        "    subgraph CI_LAYER[\"Invoicing Layer\"]\n"
        "        CI[\"SAP CI\"]\n"
        "    end\n"
        "    ORDER_MGMT --> CI_LAYER\n"
        "```\n"
        "You can check transaction FKKBIX_SAMPLE in your system."
    )

    sanitized = rag_service._sanitize_and_verify_identifiers(answer_with_mermaid, passages=[])

    # The text outside the code block gets flagged
    assert "FKKBIX_SAMPLE (unverified, confirm in your system)" in sanitized
    # Inside the mermaid block, ORDER_MGMT and CI_LAYER remain completely clean!
    assert "subgraph ORDER_MGMT[\"Order Management\"]" in sanitized
    assert "subgraph CI_LAYER[\"Invoicing Layer\"]" in sanitized
    assert "ORDER_MGMT --> CI_LAYER" in sanitized
    assert "ORDER_MGMT (unverified" not in sanitized
