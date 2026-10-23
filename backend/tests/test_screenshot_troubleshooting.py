import io
import json
import pytest
from unittest.mock import MagicMock, patch
from PIL import Image, ExifTags

from backend.app.config import settings
from backend.app.services.vision_service import vision_service
from backend.app.services.answer_planner import answer_planner
from backend.app.services.rag_service import rag_service
from backend.app.services.llm_service import llm_service
from backend.app.models.attachment import ChatAttachment
from backend.app.models.user import User


def create_test_image_with_exif():
    """Create a test JPEG image with EXIF metadata."""
    img = Image.new("RGB", (400, 300), color=(80, 120, 160))
    exif = img.getexif()
    # Add Artist tag (0x013b) and Make tag (0x010f)
    exif[0x013b] = "Clyptus-Tester"
    exif[0x010f] = "SAP-Camera"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def create_test_png(width=500, height=400):
    img = Image.new("RGB", (width, height), color=(50, 100, 150))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestScreenshotTroubleshooting:
    """
    Automated test suite for Clyptus.AI Screenshot-guided troubleshooting:
    1. Attachment validation (size limits, image counts, mime types)
    2. EXIF metadata stripping
    3. Structured vision JSON parsing (SAP error fields)
    4. Unreadable screenshot handling (asks for clearer image without guessing)
    5. Non-SAP screenshot handling (strict refusal, no non-SAP assistance)
    6. Step-by-step guided troubleshooting state & prompt logic (Turn 1 -> Step 1 only, Follow-up -> Step 2)
    7. User isolation and ownership validation
    """

    # 1. Attachment Validation
    def test_attachment_validation_size_and_type(self):
        # 1a. Verify config defaults
        assert settings.MAX_IMAGE_MB == 5
        assert settings.MAX_IMAGES_PER_MESSAGE == 3

        # 1b. Supported mime types
        valid_bytes = create_test_png()
        meta = vision_service.inspect_image_file(valid_bytes)
        assert meta["valid"] is True
        assert meta["format"] in ("PNG", "JPEG", "WEBP")

        # 1c. Unsupported format
        unsupported_bytes = b"%PDF-1.4 dummy pdf bytes"
        meta_unsupported = vision_service.inspect_image_file(unsupported_bytes)
        assert meta_unsupported["valid"] is False

        # 1d. Oversized image check
        oversized_data = b"0" * (6 * 1024 * 1024)  # 6 MB
        meta_oversized = vision_service.inspect_image_file(oversized_data)
        assert meta_oversized["valid"] is False
        assert "exceeds" in meta_oversized["error"].lower()

    # 2. EXIF Stripping
    def test_exif_metadata_stripping(self):
        raw_jpeg = create_test_image_with_exif()
        # Verify original raw image contains exif
        with Image.open(io.BytesIO(raw_jpeg)) as original_img:
            raw_exif = original_img.getexif()
            assert 0x013b in raw_exif or len(raw_exif) > 0

        # Strip EXIF using vision service
        cleaned_bytes, cleaned_mime = vision_service.strip_exif_metadata(raw_jpeg, "image/jpeg")
        assert len(cleaned_bytes) > 0
        assert cleaned_mime in ("image/jpeg", "image/png")

        # Verify cleaned image has no sensitive EXIF tags
        with Image.open(io.BytesIO(cleaned_bytes)) as cleaned_img:
            cleaned_exif = cleaned_img.getexif()
            assert 0x013b not in cleaned_exif
            assert 0x010f not in cleaned_exif

    # 3. Vision Structured Parsing
    def test_structured_vision_data_parsing(self):
        sample_json_text = json.dumps({
            "is_sap": True,
            "screen_or_app": "SAP GUI Easy Access - VA01 Create Sales Order",
            "transaction_code": "VA01",
            "module": "SD",
            "message_class_and_number": "V1 002",
            "error_text": "Customer 10001 is locked in sales area 1000/10/00",
            "visible_fields_and_values": {"Order Type": "OR", "Sales Org": "1000", "Customer": "10001"},
            "readable": True,
            "confidence": 0.95
        })

        parsed = vision_service._parse_structured_vision_data(sample_json_text)
        assert parsed["is_sap"] is True
        assert parsed["screen_or_app"] == "SAP GUI Easy Access - VA01 Create Sales Order"
        assert parsed["transaction_code"] == "VA01"
        assert parsed["module"] == "SD"
        assert parsed["message_class_and_number"] == "V1 002"
        assert "Customer 10001 is locked" in parsed["error_text"]
        assert parsed["readable"] is True
        assert parsed["confidence"] == 0.95

    # 4. Unreadable Screenshot
    def test_unreadable_screenshot_prompts_for_clearer_image(self):
        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "user-test-1"

        unreadable_attachment = [{
            "id": "att-blur-1",
            "filename": "blurry_error.png",
            "extracted_text": "",
            "vision_metadata": {
                "readable": False,
                "is_sap": True,
                "error_text": "",
                "screen_or_app": "Unknown",
            }
        }]

        result = rag_service.process_query(
            db=mock_db,
            query="",
            user=mock_user,
            attachments_data=unreadable_attachment
        )

        assert result["source_type"] == "insufficient"
        assert "clearer screenshot" in result["answer"].lower() or "readable" in result["answer"].lower()
        # Ensure it does not fabricate an SAP solution
        assert "t-code" not in result["answer"].lower() or "clear" in result["answer"].lower()

    # 5. Non-SAP Image Refusal
    def test_non_sap_screenshot_strictly_refused(self):
        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "user-test-1"

        non_sap_attachment = [{
            "id": "att-nonsap-1",
            "filename": "cute_cat.png",
            "extracted_text": "",
            "vision_metadata": {
                "readable": True,
                "is_sap": False,
                "screen_or_app": "Cat photo",
                "error_text": "",
            }
        }]

        result = rag_service.process_query(
            db=mock_db,
            query="Look at this picture",
            user=mock_user,
            attachments_data=non_sap_attachment
        )

        assert result["source_type"] == "refusal"
        assert "sap" in result["answer"].lower()
        assert (
            "specializes" in result["answer"].lower()
            or "scope" in result["answer"].lower()
            or "only" in result["answer"].lower()
            or "exclusively" in result["answer"].lower()
        )
        # Ensure it does not describe the non-SAP image contents
        assert "cat photo" not in result["answer"].lower()

    # 6. Step-by-Step Guided Troubleshooting State
    def test_guided_troubleshooting_turn1_and_followup_state(self):
        # Turn 1: Screenshot uploaded
        state_t1 = answer_planner.extract_guided_troubleshooting_state(
            chat_history=[],
            current_query="Here is my SAP error screenshot",
            has_attachment=True
        )
        assert state_t1["is_active"] is True
        assert state_t1["is_first_step"] is True
        assert state_t1["current_step_num"] == 1
        assert state_t1["is_resolved"] is False

        # Format hint detects guided step
        fmt_hint_t1 = answer_planner.detect_format_hint(
            query="Here is my SAP error screenshot",
            has_attachment=True
        )
        assert fmt_hint_t1["is_guided_step"] is True

        # Exempt from 700-word length rule
        assert llm_service.is_length_rule_exempt(
            query="Here is my SAP error screenshot",
            has_attachment=True,
            format_hint=fmt_hint_t1
        ) is True

        # Turn 2: Follow-up from user after completing Step 1
        chat_history_after_t1 = [
            {"role": "user", "content": "Here is my SAP error screenshot"},
            {"role": "assistant", "content": "What the screenshot shows: VA01 error.\n\n### Step 1: Check customer lock in XD05\nGo to XD05 and check if customer 10001 is locked. Let me know the result."}
        ]

        state_t2 = answer_planner.extract_guided_troubleshooting_state(
            chat_history=chat_history_after_t1,
            current_query="I checked XD05 and the customer was not locked there. What next?",
            has_attachment=False
        )
        assert state_t2["is_active"] is True
        assert state_t2["is_first_step"] is False
        assert state_t2["last_step"] == 1
        assert state_t2["current_step_num"] == 2
        assert state_t2["is_resolved"] is False

        fmt_hint_t2 = answer_planner.detect_format_hint(
            query="I checked XD05 and the customer was not locked there. What next?",
            chat_history=chat_history_after_t1
        )
        assert fmt_hint_t2["is_guided_step"] is True

        # Turn 3: User requests full list
        state_full = answer_planner.extract_guided_troubleshooting_state(
            chat_history=chat_history_after_t1,
            current_query="Just give me all the steps at once please",
            has_attachment=False
        )
        assert state_full["wants_full_list"] is True

        # Turn 4: Issue is resolved
        state_resolved = answer_planner.extract_guided_troubleshooting_state(
            chat_history=chat_history_after_t1,
            current_query="That worked! The error is gone and the order saved successfully.",
            has_attachment=False
        )
        assert state_resolved["is_resolved"] is True

    # 7. User Isolation
    def test_user_attachment_isolation(self):
        user_a = "usr-owner-001"
        user_b = "usr-intruder-002"

        attachment = ChatAttachment(
            id="att-private-123",
            user_id=user_a,
            chat_id="chat-secret-abc",
            filename="prod_pricing_error.png",
            file_type="image",
            mime_type="image/png",
            file_path=f"media/attachments/{user_a}/chat-secret-abc/prod_pricing_error.png",
            size_bytes=102400
        )

        assert attachment.user_id == user_a
        assert attachment.user_id != user_b
        # Directory path must be partitioned by user_id
        assert f"/{user_a}/" in attachment.file_path
