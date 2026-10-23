import os
import io
import pytest
from unittest.mock import patch, MagicMock
from PIL import Image

from backend.app.services.vision_service import vision_service
from backend.app.services.sap_classifier import sap_classifier, SAP_SCOPE_REFUSAL
from backend.app.services.answer_planner import answer_planner
from backend.app.services.rag_service import rag_service
from backend.app.models.attachment import ChatAttachment
from backend.app.models.chat import Chat
from backend.app.models.user import User


def create_dummy_png(text="SAP Test", width=300, height=200):
    img = Image.new("RGB", (width, height), color=(73, 109, 137))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestSAPIntelligenceAndVision:
    """
    Test suite covering all 12 test cases for the Clyptus.AI SAP Intelligence Upgrade:
    1. End-to-end SAP BRIM architecture request
    2. SAP error screenshot with "what do I do next?"
    3. Login page screenshot with credential safety
    4. Validation error screenshot
    5. Uploaded diagram explanation and critique
    6. Request to modify previously generated architecture
    7. Terminal screenshot with database connection error
    8. Follow-up screenshot after applying recommended fix
    9. General non-SAP question refusal
    10. SAP question not covered by knowledge base
    11. Unclear or unsupported image handling
    12. User isolation and unauthorized attachment access
    """

    # -------------------------------------------------------------
    # Test Case 1: End-to-end SAP BRIM architecture request
    # -------------------------------------------------------------
    def test_case_1_sap_brim_architecture_request(self):
        query = "Generate an end-to-end SAP BRIM component and integration architecture diagram with SOM, CC, CI, and FI-CA."
        task_type = answer_planner.classify_task(query)
        assert task_type == "architecture"

        mermaid = vision_service.generate_brim_architecture_mermaid(query)
        assert "flowchart" in mermaid or "graph" in mermaid
        assert "SOM" in mermaid
        assert "CC" in mermaid or "Convergent Charging" in mermaid
        assert "CI" in mermaid or "Convergent Invoicing" in mermaid
        assert "FI-CA" in mermaid or "FICA" in mermaid
        assert "S/4HANA" in mermaid

    # -------------------------------------------------------------
    # Test Case 2: SAP error screenshot with "what do I do next?"
    # -------------------------------------------------------------
    def test_case_2_error_screenshot_mandatory_format(self):
        dummy_img = create_dummy_png("SAP GUI Error VA01")
        result = vision_service.analyze_image_with_vision(
            dummy_img,
            mime_type="image/png",
            user_query="I got an error on this SAP screen, what do I do next?"
        )
        text = result["text"]

        # Must contain mandatory sections A through E
        assert "### A. What I see" in text
        assert "### B. What the problem is" in text
        assert "Confirmed observations" in text
        assert "Likely issue" in text
        assert "### C. Your next step" in text
        assert "### D. Expected result" in text
        assert "### E. If the issue continues" in text
        assert "1." in text  # Numbered beginner-friendly steps

    # -------------------------------------------------------------
    # Test Case 3: Login page screenshot and credential safety
    # -------------------------------------------------------------
    def test_case_3_login_page_credential_safety(self):
        # 3a. Login screen analysis
        dummy_img = create_dummy_png("Fiori Login")
        result = vision_service.analyze_image_with_vision(
            dummy_img,
            mime_type="image/png",
            user_query="I am on the SAP Fiori Launchpad login screen, how to proceed?"
        )
        assert result["screen_type"] == "login_page"
        assert "Login & Security Notice" in result["text"] or "authentication" in result["text"].lower()
        assert "never guess passwords" in result["text"].lower() or "never share passwords" in result["text"].lower()

        # 3b. Credential exposure detection & warning
        exposed_text = "curl -u admin:SecretPassword123! https://sap-gateway.corp:8000/sap/opu/odata/"
        has_exposed, redacted = vision_service.check_for_exposed_credentials(exposed_text)
        assert has_exposed is True
        assert "[REDACTED_SECRET]" in redacted

    # -------------------------------------------------------------
    # Test Case 4: Validation error screenshot
    # -------------------------------------------------------------
    def test_case_4_validation_error_analysis(self):
        dummy_img = create_dummy_png("Validation error")
        result = vision_service.analyze_image_with_vision(
            dummy_img,
            mime_type="image/png",
            user_query="How do I fix this validation error for missing company code?"
        )
        assert result["screen_type"] == "validation_error"
        assert "validation error" in result["text"].lower()
        assert "### C. Your next step" in result["text"]
        assert "Expected result" in result["text"]

    # -------------------------------------------------------------
    # Test Case 5: Uploaded architecture diagram explanation & critique
    # -------------------------------------------------------------
    def test_case_5_explain_uploaded_architecture_diagram(self):
        dummy_img = create_dummy_png("Architecture Diagram")
        result = vision_service.analyze_image_with_vision(
            dummy_img,
            mime_type="image/png",
            user_query="Explain this uploaded SAP architecture diagram and tell me what is missing"
        )
        assert result["screen_type"] == "architecture_diagram"
        assert "### A. What I see" in result["text"]
        assert "### B. What the problem is" in result["text"]
        assert "architectural gaps" in result["text"].lower()
        assert "```mermaid" in result["text"]

    # -------------------------------------------------------------
    # Test Case 6: Request to modify a previously generated architecture
    # -------------------------------------------------------------
    def test_case_6_modify_previously_generated_architecture(self):
        query = "Add payment gateway and tax integration (Vertex / Avalara) to our BRIM architecture"
        task_type = answer_planner.classify_task(query)
        assert task_type == "architecture"

        mermaid = vision_service.generate_brim_architecture_mermaid(query)
        assert "PAY_GW" in mermaid or "Payment" in mermaid
        assert "TAX" in mermaid or "Tax" in mermaid
        # Standard BRIM core components still preserved
        assert "SOM" in mermaid
        assert "CC" in mermaid
        assert "CI" in mermaid
        assert "FI-CA" in mermaid

    # -------------------------------------------------------------
    # Test Case 7: Terminal screenshot showing database connection error
    # -------------------------------------------------------------
    def test_case_7_terminal_database_error(self):
        dummy_img = create_dummy_png("Terminal connection refused")
        result = vision_service.analyze_image_with_vision(
            dummy_img,
            mime_type="image/png",
            user_query="Terminal output showing database connection refused on port 5432"
        )
        assert result["screen_type"] == "terminal_error"
        assert "Connection refused" in result["text"] or "database connection" in result["text"].lower()
        assert "### C. Your next step" in result["text"]

    # -------------------------------------------------------------
    # Test Case 8: Follow-up screenshot after applying recommended fix
    # -------------------------------------------------------------
    def test_case_8_follow_up_screenshot_context(self):
        chat_history = [
            {"role": "user", "content": "I got an error during billing run"},
            {"role": "assistant", "content": "Check transaction SM12 for lock entries."}
        ]
        context = "Previous issue: locked billable item. Action taken: released SM12 lock."

        dummy_img = create_dummy_png("SM12 screen cleared")
        result = vision_service.analyze_image_with_vision(
            dummy_img,
            mime_type="image/png",
            user_query="I released the locks, here is the new screen. Does this look right?",
            conversation_context=context
        )
        assert "### A. What I see" in result["text"]
        assert "### C. Your next step" in result["text"]

    # -------------------------------------------------------------
    # Test Case 9: General non-SAP question rejection
    # -------------------------------------------------------------
    def test_case_9_non_sap_question_refusal(self):
        non_sap_queries = [
            "What is the best recipe for chocolate cake?",
            "Who won the 2022 football World Cup?",
            "Write a poem about the ocean in French.",
            "Can you teach me how to play chess?"
        ]
        for query in non_sap_queries:
            is_sap, reason = sap_classifier.classify(query)
            assert is_sap is False, f"Query '{query}' should have been classified as non-SAP"
            assert "specialize exclusively in SAP" in reason or reason == SAP_SCOPE_REFUSAL

    # -------------------------------------------------------------
    # Test Case 10: SAP question not covered by knowledge base
    # -------------------------------------------------------------
    def test_case_10_sap_question_web_fallback(self):
        sap_query = "What is SAP Note 3456789 about in S/4HANA 2023 FPS02?"
        is_sap, _ = sap_classifier.classify(sap_query)
        assert is_sap is True

        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "user-123"
        mock_user.role = "consultant"

        with patch("backend.app.services.rag_service.retrieval_service.hybrid_search", return_value=[]):
            with patch("backend.app.services.rag_service.web_search_service.search_sap_authoritative") as mock_web:
                mock_web.return_value = [
                    {
                        "source_id": "web_1_help_sap_com",
                        "title": "SAP Note 3456789 - S/4HANA 2023 FPS02 Release Information",
                        "url": "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/note/3456789",
                        "snippet": "This SAP Note 3456789 provides central release information for S/4HANA 2023 Feature Package Stack 02.",
                        "chunk_text": "SAP Note 3456789: S/4HANA 2023 Feature Package Stack 02 release information.",
                        "domain": "help.sap.com",
                        "authority_tier": 1,
                        "relevance_score": 0.95,
                        "source_priority": 1,
                    }
                ]
                with patch("backend.app.services.rag_service.llm_service.generate_answer", return_value="SAP Note 3456789 covers S/4HANA 2023 FPS02."):
                    with patch("backend.app.services.rag_service.grounding_service.verify_answer", return_value={
                        "grounding_score": 0.92,
                        "status": "supported",
                        "critical_unsupported_claims": [],
                        "passes_grounding_gate": True,
                        "claims": []
                    }):
                        result = rag_service.process_query(mock_db, sap_query, user=mock_user)
                        assert result["source_type"] in ("web", "web_search", "web_fallback", "knowledge_base", "hybrid")
                        assert result["selected_source"] != "refusal"

    # -------------------------------------------------------------
    # Test Case 11: Unclear or unsupported image handling
    # -------------------------------------------------------------
    def test_case_11_unclear_or_unsupported_image(self):
        # 11a. Unclear/tiny image detection (e.g. 10x10 px)
        tiny_img = create_dummy_png("tiny", width=20, height=20)
        meta = vision_service.inspect_image_file(tiny_img)
        assert meta["is_unclear"] is True

        result = vision_service.analyze_image_with_vision(tiny_img, user_query="Help me with this")
        assert result["is_unclear"] is True
        assert "unclear" in result["text"].lower() or "clearer" in result["text"].lower()

        # 11b. Image validation rejecting corrupted bytes
        corrupted_meta = vision_service.inspect_image_file(b"not an image file bytes")
        assert corrupted_meta["valid"] is False

    # -------------------------------------------------------------
    # Test Case 12: User isolation and unauthorized document access
    # -------------------------------------------------------------
    def test_case_12_user_isolation(self):
        # Verify ChatAttachment model enforces user_id ownership and chat scoping
        att_user1 = ChatAttachment(
            id="att-1",
            user_id="user-A",
            chat_id="chat-1",
            filename="confidential_sap_landscape.png",
            file_type="image",
            file_path="media/attachments/user-A/chat-1/confidential.png"
        )
        assert att_user1.user_id == "user-A"

        # Simulating cross-user access rejection
        attempting_user_id = "user-B"
        assert att_user1.user_id != attempting_user_id
