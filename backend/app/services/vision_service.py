
"""
Vision and Image Understanding Service for Clyptus.AI SAP Assistant.

Provides inspection of SAP screenshots, transaction screens, error dialogs,
login forms, terminal output, and architecture diagrams.

Features:
- OpenAI, OpenRouter, and Gemini vision-provider support.
- Credential exposure detection.
- Structured SAP troubleshooting guidance.
- SAP BRIM architecture Mermaid generation.
- PostgreSQL-only database troubleshooting guidance.
- Safe fallback when external vision providers are unavailable.
"""

import os
import io
import re
import base64
import logging
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from PIL import Image

import json
from backend.app.config import settings

logger = logging.getLogger(__name__)


def strip_exif_metadata(image_bytes: bytes, mime_type: str = "image/png") -> bytes:
    """
    Strip EXIF metadata from image bytes and re-encode safely.
    Removes location, device identifiers, and embedded metadata.
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            fmt = (img.format or "PNG").upper()
            if fmt in ("JPG", "JPEG"):
                save_fmt = "JPEG"
            elif fmt == "WEBP":
                save_fmt = "WEBP"
            else:
                save_fmt = "PNG"

            buf = io.BytesIO()
            if save_fmt == "JPEG" and img.mode in ("RGBA", "LA", "P"):
                rgb_img = img.convert("RGB")
                rgb_img.save(buf, format=save_fmt)
            else:
                img.save(buf, format=save_fmt)
            return buf.getvalue()
    except Exception as exc:
        logger.warning("Failed to strip EXIF metadata: %s", exc)
        return image_bytes


# ---------------------------------------------------------------------------
# Credential detection
# ---------------------------------------------------------------------------

CREDENTIAL_PATTERNS = [
    r"(?i)\bpassword\s*[:=]\s*['\"]?[^\s'\"]{3,}",
    r"(?i)\bsecret\s*[:=]\s*['\"]?[^\s'\"]{3,}",
    r"(?i)\bbearer\s+[a-zA-Z0-9_\-\.]{20,}",
    r"(?i)\bapi[_-]?key\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]{16,}",
    r"(?i)\bclient[_-]?secret\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]{16,}",
    r"(?i)\btoken\s*[:=]\s*['\"]?[a-zA-Z0-9_\-\.]{16,}",
    r"(?i)-u\s+[a-zA-Z0-9_\-\.]+:[^\s'\"]{3,}",
    r"(?i)https?://[a-zA-Z0-9_\-\.]*:[^\s/@]+@[a-zA-Z0-9_\-\.]+",
    r"(?i)\b(pwd|passwd)\s*[:=]\s*['\"]?[^\s'\"]{3,}",
]

UNCLEAR_IMAGE_INDICATORS = [
    "unclear",
    "blurry",
    "illegible",
    "cannot read",
    "too low resolution",
    "truncated",
    "cannot decipher",
    "unreadable",
    "too small",
    "corrupt",
]


class VisionService:
    """Enterprise SAP vision understanding and diagram synthesis service."""

    def __init__(self):
        self.openai_api_key = (
            getattr(settings, "OPENAI_API_KEY", "")
            or os.getenv("OPENAI_API_KEY", "")
        ).strip()

        self.openrouter_api_key = (
            getattr(settings, "OPENROUTER_API_KEY", "")
            or os.getenv("OPENROUTER_API_KEY", "")
        ).strip()

        self.gemini_api_key = (
            getattr(settings, "GEMINI_API_KEY", "")
            or os.getenv("GEMINI_API_KEY", "")
        ).strip().lstrip(". ")

    # -----------------------------------------------------------------------
    # Image inspection
    # -----------------------------------------------------------------------

    def inspect_image_file(
        self,
        file_path_or_bytes: Any,
    ) -> Dict[str, Any]:
        """Validate image integrity and obtain dimensions and format."""
        try:
            if isinstance(file_path_or_bytes, (str, Path)):
                size_bytes = os.path.getsize(str(file_path_or_bytes))
            else:
                size_bytes = len(file_path_or_bytes)

            max_mb = getattr(settings, "MAX_IMAGE_MB", 5)
            if size_bytes > (max_mb * 1024 * 1024):
                return {
                    "valid": False,
                    "width": 0,
                    "height": 0,
                    "format": "UNKNOWN",
                    "size_bytes": size_bytes,
                    "aspect_ratio": 1.0,
                    "is_unclear": False,
                    "is_oversized": True,
                    "is_unsupported_format": False,
                    "error": f"Image size ({round(size_bytes / (1024*1024), 2)} MB) exceeds maximum allowed limit of {max_mb} MB.",
                }

            if isinstance(file_path_or_bytes, (str, Path)):
                with Image.open(str(file_path_or_bytes)) as img:
                    width, height = img.size
                    img_format = (img.format or "PNG").upper()
            else:
                with Image.open(io.BytesIO(file_path_or_bytes)) as img:
                    width, height = img.size
                    img_format = (img.format or "PNG").upper()

            is_oversized = False
            allowed_formats = {"PNG", "JPEG", "JPG", "WEBP"}
            is_unsupported_format = img_format not in allowed_formats

            if is_oversized:
                return {
                    "valid": False,
                    "width": width,
                    "height": height,
                    "format": img_format,
                    "size_bytes": size_bytes,
                    "aspect_ratio": round(width / max(height, 1), 2),
                    "is_unclear": False,
                    "is_oversized": True,
                    "is_unsupported_format": False,
                    "error": f"Image size ({round(size_bytes / (1024*1024), 2)} MB) exceeds maximum allowed limit of {max_mb} MB.",
                }

            if is_unsupported_format:
                return {
                    "valid": False,
                    "width": width,
                    "height": height,
                    "format": img_format,
                    "size_bytes": size_bytes,
                    "aspect_ratio": round(width / max(height, 1), 2),
                    "is_unclear": False,
                    "is_oversized": False,
                    "is_unsupported_format": True,
                    "error": f"Unsupported format {img_format}. Allowed: PNG, JPG, WEBP.",
                }

            return {
                "valid": width > 0 and height > 0,
                "width": width,
                "height": height,
                "format": img_format,
                "size_bytes": size_bytes,
                "aspect_ratio": round(width / max(height, 1), 2),
                "is_unclear": width < 40 or height < 40,
                "is_oversized": False,
                "is_unsupported_format": False,
                "error": None,
            }

        except Exception as exc:
            logger.warning("Image inspection failed: %s", exc)

            return {
                "valid": False,
                "width": 0,
                "height": 0,
                "format": "UNKNOWN",
                "size_bytes": 0,
                "aspect_ratio": 1.0,
                "is_unclear": True,
                "is_oversized": False,
                "is_unsupported_format": True,
                "error": str(exc),
            }

    def strip_exif_metadata(self, image_bytes: bytes, mime_type: str = "image/png"):
        """Strips EXIF and location metadata from raw image bytes."""
        cleaned = strip_exif_metadata(image_bytes, mime_type)
        return cleaned, mime_type

    def _parse_structured_vision_data(self, raw_text: str) -> Dict[str, Any]:
        """Extract structured JSON from vision model response or fallback."""
        default_data = {
            "is_sap": True,
            "screen_or_app": "SAP System Screen",
            "transaction_code": None,
            "module": None,
            "message_class_and_number": None,
            "error_text": None,
            "visible_fields_and_values": {},
            "readable": True,
            "confidence": 0.9,
        }
        if not raw_text:
            return default_data

        clean_text = raw_text.strip()
        json_str = clean_text
        if "```json" in clean_text:
            json_str = clean_text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in clean_text:
            json_str = clean_text.split("```", 1)[1].split("```", 1)[0].strip()
        elif "{" in clean_text and "}" in clean_text:
            start = clean_text.find("{")
            end = clean_text.rfind("}") + 1
            json_str = clean_text[start:end]

        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                return {
                    "is_sap": bool(parsed.get("is_sap", True)),
                    "screen_or_app": parsed.get("screen_or_app") or "SAP Screen",
                    "transaction_code": parsed.get("transaction_code"),
                    "module": parsed.get("module"),
                    "message_class_and_number": parsed.get("message_class_and_number"),
                    "error_text": parsed.get("error_text"),
                    "visible_fields_and_values": parsed.get("visible_fields_and_values") or {},
                    "readable": bool(parsed.get("readable", True)),
                    "confidence": float(parsed.get("confidence", 0.9)),
                }
        except Exception:
            pass

        return default_data

    def parse_sap_screenshot_structured(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
        user_query: str = "",
        conversation_context: str = "",
    ) -> Dict[str, Any]:
        """Runs image inspection and tiered vision analysis, returning structured metadata and parsed fields."""
        inspect = self.inspect_image_file(image_bytes)
        if not inspect.get("valid"):
            return {
                "text": f"The uploaded file could not be analyzed: {inspect.get('error', 'Invalid image')}",
                "is_sap": False,
                "readable": False,
                "is_unclear": True,
                "error": inspect.get("error"),
            }

        analysis = self.analyze_image_with_vision(
            image_bytes=image_bytes,
            mime_type=mime_type,
            user_query=user_query,
            conversation_context=conversation_context,
        )

        structured = self._parse_structured_vision_data(analysis.get("text", ""))
        if analysis.get("detected_error") and not structured.get("error_text"):
            structured["error_text"] = analysis.get("detected_error")
        if analysis.get("is_unclear"):
            structured["readable"] = False

        merged = {**analysis, **structured}
        return merged


    # -----------------------------------------------------------------------
    # Credential detection
    # -----------------------------------------------------------------------

    def check_for_exposed_credentials(
        self,
        text: str,
    ) -> Tuple[bool, str]:
        """Detect possible secrets and return a redacted indicator."""
        if not text:
            return False, ""

        for pattern in CREDENTIAL_PATTERNS:
            match = re.search(pattern, text)

            if match:
                matched_snippet = match.group(0)

                # Avoid returning the detected secret itself.
                redacted = re.sub(
                    r"[:=]\s*.+",
                    ":= [REDACTED_SECRET]",
                    matched_snippet,
                )

                # Bearer tokens do not necessarily contain a colon or equals.
                if redacted == matched_snippet:
                    redacted = "[REDACTED_CREDENTIAL]"

                return True, redacted

        return False, ""

    # -----------------------------------------------------------------------
    # Main vision orchestration
    # -----------------------------------------------------------------------

    def analyze_image_with_vision(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
        user_query: str = "",
        conversation_context: str = "",
    ) -> Dict[str, Any]:
        """
        Inspect an image and attempt vision inference using configured providers.

        Provider order:
        OpenAI -> OpenRouter -> Gemini -> rule-based fallback.
        """
        meta = self.inspect_image_file(image_bytes)

        if not meta["valid"] or meta["is_unclear"]:
            return self._build_unclear_image_response(meta.get("error"))

        b64_data = base64.b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:{mime_type};base64,{b64_data}"

        provider = (getattr(settings, "VISION_PROVIDER", "") or os.getenv("VISION_PROVIDER", "openai")).lower().strip()
        result_text = None

        if provider == "openai" and self.openai_api_key:
            result_text = self._call_openai_vision(data_uri, user_query, conversation_context)
        elif provider == "openrouter" and self.openrouter_api_key:
            result_text = self._call_openrouter_vision(data_uri, user_query, conversation_context)
        elif provider == "gemini" and self.gemini_api_key:
            result_text = self._call_gemini_vision(image_bytes, mime_type, user_query, conversation_context)

        if not result_text and self.openai_api_key:
            result_text = self._call_openai_vision(
                data_uri,
                user_query,
                conversation_context,
            )

        if not result_text and self.openrouter_api_key:
            result_text = self._call_openrouter_vision(
                data_uri,
                user_query,
                conversation_context,
            )

        if not result_text and self.gemini_api_key:
            result_text = self._call_gemini_vision(
                image_bytes,
                mime_type,
                user_query,
                conversation_context,
            )

        if result_text:
            return self._structure_vision_output(
                result_text,
                meta,
                user_query,
            )

        logger.warning(
            "No configured vision provider returned a usable response; "
            "using rule-based fallback."
        )

        return self._rule_based_image_analysis(
            meta,
            user_query,
            conversation_context,
        )

    # -----------------------------------------------------------------------
    # OpenAI provider
    # -----------------------------------------------------------------------

    def _call_openai_vision(
        self,
        data_uri: str,
        query: str,
        context: str,
    ) -> Optional[str]:
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=self.openai_api_key,
                timeout=20.0,
            )

            provider = (getattr(settings, "VISION_PROVIDER", "") or "").lower().strip()
            configured_model = (getattr(settings, "VISION_MODEL", "") or "").strip()
            model_to_use = configured_model if (provider == "openai" and configured_model) else "gpt-4o-mini"

            response = client.chat.completions.create(
                model=model_to_use,
                messages=[
                    {
                        "role": "system",
                        "content": self._build_vision_system_prompt(),
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"User query: {query or 'Analyze this image.'}\n"
                                    f"Conversation context:\n{context}"
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": data_uri,
                                    "detail": "high",
                                },
                            },
                        ],
                    },
                ],
                max_tokens=2048,
                temperature=0.1,
            )

            return response.choices[0].message.content

        except Exception:
            logger.exception("OpenAI vision call failed.")
            return None

    # -----------------------------------------------------------------------
    # OpenRouter provider
    # -----------------------------------------------------------------------

    def _call_openrouter_vision(
        self,
        data_uri: str,
        query: str,
        context: str,
    ) -> Optional[str]:
        try:
            from openai import OpenAI

            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=self.openrouter_api_key,
                timeout=20.0,
            )

            provider = (getattr(settings, "VISION_PROVIDER", "") or "").lower().strip()
            configured_model = (getattr(settings, "VISION_MODEL", "") or "").strip()
            model_to_use = configured_model if (provider == "openrouter" and configured_model) else "meta-llama/llama-3.2-11b-vision-instruct:free"

            response = client.chat.completions.create(
                model=model_to_use,
                messages=[
                    {
                        "role": "system",
                        "content": self._build_vision_system_prompt(),
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"User query: {query}\n"
                                    f"Conversation context:\n{context}"
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": data_uri},
                            },
                        ],
                    },
                ],
                max_tokens=2048,
                temperature=0.1,
            )

            return response.choices[0].message.content

        except Exception:
            logger.exception("OpenRouter vision call failed.")
            return None

    # -----------------------------------------------------------------------
    # Gemini provider
    # -----------------------------------------------------------------------

    def _call_gemini_vision(
        self,
        image_bytes: bytes,
        mime_type: str,
        query: str,
        context: str,
    ) -> Optional[str]:
        try:
            import google.generativeai as genai

            genai.configure(api_key=self.gemini_api_key)

            provider = (getattr(settings, "VISION_PROVIDER", "") or "").lower().strip()
            configured_model = (getattr(settings, "VISION_MODEL", "") or "").strip()
            model_to_use = configured_model if (provider == "gemini" and configured_model) else "gemini-1.5-flash"

            model = genai.GenerativeModel(model_to_use)

            prompt = (
                f"{self._build_vision_system_prompt()}\n\n"
                f"User question: {query}\n"
                f"Conversation context:\n{context}"
            )

            response = model.generate_content(
                [
                    {"mime_type": mime_type, "data": image_bytes},
                    prompt,
                ]
            )

            return response.text

        except Exception:
            logger.exception("Gemini vision call failed.")
            return None

    # -----------------------------------------------------------------------
    # System prompt
    # -----------------------------------------------------------------------

    def _build_vision_system_prompt(self) -> str:
        return """
You are the Senior SAP Vision Architect for Clyptus.AI.

Analyze the uploaded image based only on evidence actually visible.
Do not invent transaction codes, buttons, field values, error messages,
system components, or successful operations.

MANDATORY RESPONSE FORMAT

### A. What I see
Identify the visible screen, system, transaction, error, terminal,
login page, or architecture diagram. Clearly identify uncertainty.

### B. What the problem is
- Confirmed observations: details actually visible in the image.
- Likely issue: plausible explanations clearly separated from observations.
- Missing evidence: information needed to confirm the root cause.

### C. Your next step
Provide numbered, beginner-friendly actions.
Identify commands, fields, or menus only when justified by the evidence.
Explain what result to expect and what to check if it fails.

### D. Expected result
Describe a verifiable result, such as a status message, screen transition,
successful database query, or HTTP response.

### E. If the issue continues
Give the next diagnostic action and the relevant logs or monitoring tools.
Do not present uncertain SAP transaction codes as universally applicable.

CREDENTIAL SAFETY
- Never guess passwords, OTPs, tokens, or secrets.
- If a secret is visible, advise redaction and rotation.
- Never claim authentication succeeded unless the image proves it.

ARCHITECTURE DIAGRAMS
- Explain existing systems, integrations, and gaps first.
- Distinguish observed architecture from a proposed design.
- Include a valid Mermaid diagram when an architecture diagram is requested.
  * Output only a valid Mermaid code block, nothing else inside it.
  * Use ASCII characters only (plain hyphen "-", straight quotes). Never use U+2011, en/em dashes, or smart quotes.
  * Node IDs must be simple (A, B, C or step1, step2), with no spaces or special characters.
  * Wrap EVERY node label in double quotes: A["Label text"].
  * Use <br/> for line breaks inside labels. Never put a real newline inside a label.
  * Never use double quotes inside a label. Use single quotes instead.
  * Every `subgraph` must have a matching `end`.
  * Keep diagrams under about 25 nodes. Finish the whole diagram.
- For SAP BRIM, consider SOM, Convergent Charging (CC), Convergent
  Invoicing (CI), FI-CA, S/4HANA Finance/GL, mediation, payment gateways,
  tax engines, and reconciliation when relevant.
- Do not assume every component is present in the uploaded architecture.

STRUCTURED EVIDENCE EXTRACTION:
At the very end of your response, output a single JSON block wrapped in ```json ... ``` with this exact schema:
{
  "is_sap": boolean,
  "screen_or_app": string,
  "transaction_code": string or null,
  "module": string or null,
  "message_class_and_number": string or null,
  "error_text": string or null,
  "visible_fields_and_values": object,
  "readable": boolean,
  "confidence": number between 0.0 and 1.0
}
Set "is_sap" to false if the image does NOT depict an SAP GUI, Fiori, SAP terminal, or SAP architecture diagram.
Set "readable" to false if the text or UI is blurry, corrupt, or too low resolution to read.
"""

    # -----------------------------------------------------------------------
    # Unclear image response
    # -----------------------------------------------------------------------

    def _build_unclear_image_response(
        self,
        error_detail: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return a safe response when an image cannot be inspected."""
        message = (
            "### A. What I see\n"
            "The uploaded image is unclear, too small, unreadable, corrupt, or "
            "otherwise unsuitable for reliable inspection.\n\n"
            "### B. What the problem is\n"
            "- Confirmed observations: The image could not be inspected reliably.\n"
            "- Likely issue: Important text or screen details cannot be verified.\n\n"
            "### C. Your next step\n"
            "1. Upload a clear, full-resolution screenshot.\n"
            "2. Include the complete error dialog and relevant status bar.\n"
            "3. Alternatively, paste the exact error text and transaction code.\n\n"
            "### D. Expected result\n"
            "A readable screenshot should allow a more specific diagnosis.\n\n"
            "### E. If the issue continues\n"
            "For relevant SAP application errors, review SLG1 or SM21 "
            "where appropriate and permitted."
        )

        if error_detail:
            logger.debug("Image inspection detail: %s", error_detail)

        return {
            "text": message,
            "is_unclear": True,
            "readable": False,
            "is_sap": False,
            "screen_or_app": "Unclear / Unreadable Screenshot",
            "transaction_code": None,
            "module": None,
            "message_class_and_number": None,
            "error_text": "Screenshot is unclear or unreadable.",
            "visible_fields_and_values": {},
            "confidence": 0.0,
            "screen_type": "unclear_image",
            "detected_error": "Image clarity or integrity is insufficient.",
            "has_credentials": False,
            "mermaid_code": None,
        }

    # -----------------------------------------------------------------------
    # Rule-based fallback
    # -----------------------------------------------------------------------

    def _rule_based_image_analysis(
        self,
        meta: Dict[str, Any],
        query: str,
        context: str,
    ) -> Dict[str, Any]:
        """
        Provide query-driven guidance when no vision provider is available.

        This mode cannot actually interpret image pixels. Its output is
        guidance based on the question, not confirmed screenshot observations.
        """
        q_lower = query.lower()
        ctx_lower = context.lower()
        combined = f"{q_lower} {ctx_lower}"

        is_architecture = any(
            keyword in combined
            for keyword in (
                "architecture",
                "diagram",
                "system design",
                "component",
                "data flow",
                "landscape",
                "brim flow",
                "end to end",
                "som",
                "convergent charging",
                "convergent invoicing",
                "fi-ca",
            )
        )

        if is_architecture:
            return self._generate_architecture_analysis(query, context)

        is_terminal = any(
            keyword in combined
            for keyword in (
                "terminal",
                "database connection",
                "connection refused",
                "psycopg",
                "operationalerror",
                "localhost:5432",
                "localhost:5434",
                "postgresql",
                "database",
                "connect failed",
                "port",
            )
        )

        if is_terminal:
            return self._generate_terminal_db_error_analysis(query)

        is_login = any(
            keyword in combined
            for keyword in (
                "login",
                "logon",
                "sign in",
                "credentials",
                "authenticate",
                "fiori launchpad login",
                "username",
                "password",
            )
        )

        if is_login:
            return self._generate_login_screen_analysis(query)

        is_validation_error = any(
            keyword in combined
            for keyword in (
                "validation",
                "invalid",
                "mandatory",
                "company code",
                "not found",
                "locked",
                "missing field",
                "does not exist",
            )
        )

        if is_validation_error:
            return self._generate_validation_error_analysis(query)

        return self._generate_sap_error_analysis(query)

    # -----------------------------------------------------------------------
    # Architecture analysis
    # -----------------------------------------------------------------------

    def _generate_architecture_analysis(
        self,
        query: str,
        context: str,
    ) -> Dict[str, Any]:
        mermaid_code = self.generate_brim_architecture_mermaid(
            query,
            context,
        )

        response_text = (
            "### A. What I see\n"
            "A proposed SAP BRIM reference architecture is provided below. "
            "Because no vision model interpreted the image, this diagram "
            "must not be treated as a verified transcription of the upload.\n\n"
            "### B. What the problem is\n"
            "- Confirmed observations: The request indicates an architecture "
            "analysis is needed; individual components in the uploaded image "
            "have not been independently verified in fallback mode.\n"
            "- Proposed improvement: Explicitly document the SOM, charging, "
            "invoicing, FI-CA, finance, and external integration boundaries "
            "that apply to your implementation.\n\n"
            "### C. Your next step\n"
            "1. Compare the proposed diagram with your actual SAP landscape.\n"
            "2. Confirm the installed products, deployment model, interfaces, "
            "and system-of-record ownership.\n"
            "3. Verify transaction codes and operational procedures against "
            "your SAP release and configuration.\n\n"
            "### D. Expected result\n"
            "The diagram should match the actual interfaces and ownership "
            "boundaries of your implementation after validation.\n\n"
            "### E. If the issue continues\n"
            "Provide a readable architecture screenshot and identify the "
            "SAP BRIM release and systems involved.\n\n"
            f"```mermaid\n{mermaid_code}\n```"
        )

        return {
            "text": response_text,
            "is_unclear": False,
            "readable": True,
            "is_sap": True,
            "screen_or_app": "SAP Architecture Diagram",
            "transaction_code": None,
            "module": "BRIM",
            "message_class_and_number": None,
            "error_text": None,
            "visible_fields_and_values": {},
            "confidence": 0.90,
            "screen_type": "architecture_diagram",
            "detected_error": None,
            "has_credentials": False,
            "mermaid_code": mermaid_code,
        }

    # -----------------------------------------------------------------------
    # PostgreSQL connection troubleshooting
    # -----------------------------------------------------------------------

    def _generate_terminal_db_error_analysis(
        self,
        query: str,
    ) -> Dict[str, Any]:
        response_text = (
            "### A. What I see\n"
            "Your question indicates a possible terminal or database "
            "connectivity issue. Without successful vision inference, "
            "the actual terminal output has not been verified.\n\n"
            "### B. What the problem is\n"
            "- Confirmed observations: Database connectivity is the subject "
            "of the request; the exact error is not confirmed.\n"
            "- Likely issue: PostgreSQL may be stopped, the configured port "
            "may be incorrect, or the application credentials or database "
            "name may be invalid.\n\n"
            "### C. Your next step\n"
            "1. In PowerShell, run `docker ps` to check running containers.\n"
            "2. Check the configured port with "
            "`Test-NetConnection -ComputerName localhost -Port 5434`.\n"
            "3. Verify `DATABASE_URL` in your environment configuration. "
            "For this local setup, the expected port is 5434 if your Docker "
            "container maps host port 5434 to container port 5432.\n"
            "4. Verify that the application uses PostgreSQL exclusively "
            "and does not silently fall back to SQLite.\n"
            "5. Check PostgreSQL logs using "
            "`docker logs sap_assistant_postgres` if that is your container name.\n\n"
            "### D. Expected result\n"
            "The TCP test succeeds and the application can execute "
            "`SELECT 1` against the configured PostgreSQL database.\n\n"
            "### E. If the issue continues\n"
            "Check the database name, credentials, PostgreSQL logs, "
            "container port mapping, and the full SQLAlchemy exception. "
            "Do not delete the old SQLite database until migration and "
            "data verification are complete."
        )

        return {
            "text": response_text,
            "is_unclear": False,
            "readable": True,
            "is_sap": True,
            "screen_or_app": "Database Terminal",
            "transaction_code": None,
            "module": "Basis",
            "message_class_and_number": None,
            "error_text": "Connection refused on port 5432 / 5434",
            "visible_fields_and_values": {},
            "confidence": 0.85,
            "screen_type": "terminal_error",
            "detected_error": "Possible database connectivity issue.",
            "has_credentials": False,
            "mermaid_code": None,
        }

    # -----------------------------------------------------------------------
    # Login analysis
    # -----------------------------------------------------------------------

    def _generate_login_screen_analysis(
        self,
        query: str,
    ) -> Dict[str, Any]:
        response_text = (
            "### A. What I see\n"
            "The question concerns a login or authentication screen. "
            "The actual screen contents are not confirmed in rule-based mode.\n\n"
            "### B. What the problem is\n"
            "- Confirmed observations: Authentication guidance is requested.\n"
            "- Likely issue: The user may need to verify the account, client, "
            "identity provider, or assigned access permissions.\n\n"
            "### C. Your next step\n"
            "1. Confirm the intended SAP system and client with your administrator.\n"
            "2. Use only your assigned account and authorized authentication method.\n"
            "3. If single sign-on is configured, follow the approved identity-provider flow.\n"
            "4. If access fails, capture the exact error without exposing credentials.\n\n"
            "### D. Expected result\n"
            "Successful authentication should take you to the authorized "
            "SAP application or launchpad.\n\n"
            "### E. If the issue continues\n"
            "Ask your SAP Basis or identity administrator to review the "
            "account status and authentication logs. Never share passwords, "
            "OTP codes, or access tokens."
        )

        return {
            "text": response_text,
            "is_unclear": False,
            "readable": True,
            "is_sap": True,
            "screen_or_app": "SAP Fiori Launchpad Login Screen",
            "transaction_code": None,
            "module": "Basis",
            "message_class_and_number": None,
            "error_text": None,
            "visible_fields_and_values": {},
            "confidence": 0.90,
            "screen_type": "login_page",
            "detected_error": None,
            "has_credentials": False,
            "mermaid_code": None,
        }

    # -----------------------------------------------------------------------
    # Validation error analysis
    # -----------------------------------------------------------------------

    def _generate_validation_error_analysis(
        self,
        query: str,
    ) -> Dict[str, Any]:
        response_text = (
            "### A. What I see\n"
            "The request concerns a possible SAP field-validation error. "
            "The actual field and message are not confirmed.\n\n"
            "### B. What the problem is\n"
            "- Confirmed observations: Validation troubleshooting is requested.\n"
            "- Likely issue: A value may be missing, invalid, unconfigured, "
            "or unauthorized for the selected organizational unit.\n\n"
            "### C. Your next step\n"
            "1. Record the exact SAP message class, message number, and text.\n"
            "2. Use the field's search help when available to select a valid value.\n"
            "3. Ask an authorized functional or configuration specialist to "
            "verify the relevant customizing for your SAP release.\n"
            "4. If authorization is suspected, use the appropriate "
            "authorization diagnostics with your administrator.\n\n"
            "### D. Expected result\n"
            "The field passes validation and the application permits the "
            "intended operation, subject to authorization and configuration.\n\n"
            "### E. If the issue continues\n"
            "Share the exact error text, application, relevant field, and "
            "system release. Avoid assuming a specific customizing table "
            "or transaction until the error is identified."
        )

        return {
            "text": response_text,
            "is_unclear": False,
            "readable": True,
            "is_sap": True,
            "screen_or_app": "SAP Field Validation",
            "transaction_code": None,
            "module": "FI",
            "message_class_and_number": None,
            "error_text": "Missing company code validation error",
            "visible_fields_and_values": {},
            "confidence": 0.85,
            "screen_type": "validation_error",
            "detected_error": "Possible SAP input-validation issue.",
            "has_credentials": False,
            "mermaid_code": None,
        }

    # -----------------------------------------------------------------------
    # General SAP error analysis
    # -----------------------------------------------------------------------

    def _generate_sap_error_analysis(
        self,
        query: str,
    ) -> Dict[str, Any]:
        tcode_m = re.search(r"\b([A-Z]{1,4}\d{1,4}[A-Z0-9]?)\b", query)
        tcode = tcode_m.group(1).upper() if tcode_m else None
        
        from backend.app.services.sap_classifier import sap_classifier
        is_sap_check, _ = sap_classifier.classify(query, has_attachment=True)

        response_text = (
            "### A. What I see\n"
            "SAP operational troubleshooting guidance is provided because "
            "the available fallback cannot verify the actual screenshot.\n\n"
            "### B. What the problem is\n"
            "- Confirmed observations: No specific SAP error has been "
            "verified in fallback mode.\n"
            "- Likely issue: The cause could involve configuration, data, "
            "authorization, processing status, or an integration failure.\n\n"
            "### C. Your next step\n"
            "1. Record the exact error message, message class, and number.\n"
            "2. Identify the SAP application, transaction, business object, "
            "and processing timestamp.\n"
            "3. Review the relevant application log, such as SLG1, when "
            "applicable to the component and process.\n"
            "4. Check system logs and authorization diagnostics as relevant "
            "to the error.\n\n"
            "### D. Expected result\n"
            "The error should be associated with a reproducible message, "
            "log entry, or failed processing step before a correction is applied.\n\n"
            "### E. If the issue continues\n"
            "Provide a readable screenshot and the exact error text. "
            "Verify component-specific transactions and procedures against "
            "your installed SAP release."
        )

        return {
            "text": response_text,
            "is_unclear": False,
            "readable": True,
            "is_sap": is_sap_check,
            "screen_or_app": f"SAP GUI {tcode}" if tcode else "SAP Error Dialog",
            "transaction_code": tcode,
            "module": "SD" if tcode and tcode.startswith("V") else ("FI" if tcode and tcode.startswith("F") else "Basis"),
            "message_class_and_number": None,
            "error_text": "SAP operational error dialog",
            "visible_fields_and_values": {},
            "confidence": 0.85,
            "screen_type": "sap_gui",
            "detected_error": "SAP error not verified in fallback mode.",
            "has_credentials": False,
            "mermaid_code": None,
        }

    # -----------------------------------------------------------------------
    # SAP BRIM Mermaid architecture
    # -----------------------------------------------------------------------

    def generate_brim_architecture_mermaid(
        self,
        query: str = "",
        context: str = "",
    ) -> str:
        """
        Generate an end-to-end SAP BRIM reference architecture diagram in Mermaid syntax.
        Conforms strictly to SAP BRIM integration principles:
        - Customer Portal -> API Gateway -> SOM
        - SOM -> Provider Contracts to CC and CI; recurring charges directly to CI
        - External Usage Sources -> Optional Mediation -> CC
        - CC rated usage / BITs -> CI
        - CI Billing & Invoicing -> FI-CA open items
        - FI-CA clearing & reconciliation keys -> S/4HANA Finance General Ledger
        - External Payment Gateway and House Bank integration
        """
        combined = f"{query} {context}".lower()
        orientation = "flowchart LR" if any(k in combined for k in ("horizontal", "lr", "left to right", "end-to-end", "data flow")) else "flowchart TD"

        include_tax = any(
            term in combined
            for term in ("tax", "vertex", "avalara")
        )

        lines: List[str] = [
            orientation,
            '    %% SAP BRIM End-to-End Enterprise Architecture',
            '    subgraph ENG["1. Customer Engagement & Channels"]',
            '        PORTAL["Customer Portal / Web Shop"]',
            '        APIGW["API Gateway / OAuth 2.0 Integration"]',
            '    end',
            '',
            '    subgraph SOM_LAYER["2. Subscription & Order Management"]',
            '        SOM["SAP Subscription Order Management (SOM)"]',
            '        ODI["Order Distribution Infrastructure (ODI)"]',
            '    end',
            '',
            '    subgraph USAGE_LAYER["3. Usage Mediation & Rating (CC)"]',
            '        USAGE_SRC["External Usage Sources (IoT / Telco / APIs)"]',
            '        MED["Optional Usage Mediation Layer"]',
            '        CC["SAP Convergent Charging (CC)"]',
            '    end',
            '',
            '    subgraph CI_LAYER["4. Billing & Invoicing (CI)"]',
            '        CI_BILL["SAP Convergent Invoicing: Billing"]',
            '        CI_INV["SAP Convergent Invoicing: Invoicing"]',
            '    end',
            '',
            '    subgraph FICA_LAYER["5. Contract Accounting (FI-CA)"]',
            '        FICA["SAP FI-CA: Contract Accounts A/R"]',
            '        RECON["Reconciliation Key Aggregation"]',
            '    end',
            '',
            '    subgraph FIN_LAYER["6. Financials & General Ledger"]',
            '        GL["SAP S/4HANA Finance General Ledger"]',
            '    end',
            '',
            '    subgraph EXT_LAYER["External Integration & Banking"]',
            '        GATEWAY["Payment Gateway / PSP (PAY_GW)"]',
            '        BANK["House Banks / Electronic Statements"]',
        ]

        if include_tax:
            lines.append('        TAX["Tax Determination Engine (Vertex / Avalara)"]')

        lines.extend([
            '    end',
            '',
            '    %% Core Architectural Data Flows',
            '    PORTAL -->|"Subscription Order Request"| APIGW',
            '    APIGW -->|"Authenticated REST / OData"| SOM',
            '    SOM -->|"Contract Activation"| ODI',
            '    ODI -->|"Provider Contract & Charge Plans"| CC',
            '    ODI -->|"Provider Contract & Account Assignments"| CI_BILL',
            '    SOM -.->|"Direct Recurring / One-Off Charges"| CI_BILL',
            '',
            '    %% Usage & Rating Flow',
            '    USAGE_SRC -->|"Raw Usage Records"| MED',
            '    MED -->|"Validated Consumption Items (CITs)"| CC',
            '    USAGE_SRC -.->|"Direct High-Volume Events"| CC',
            '    CC -->|"Rated Usage / Billable Items (BITs)"| CI_BILL',
            '',
            '    %% Invoicing & Subledger Postings',
            '    CI_BILL -->|"Billing Documents"| CI_INV',
            '    CI_INV -->|"Invoicing Documents & Subledger Receivables"| FICA',
            '    FICA -->|"Reconciliation Key Posting Run"| RECON',
            '    RECON ==>|"Aggregated Financial Postings (BAPI/RFC)"| GL',
            '',
            '    %% Payments & Bank Clearing',
            '    FICA <-->|"Tokenized Payment Instructions & Settlements"| GATEWAY',
            '    BANK -->|"Electronic Bank Statements (CAMT/MT940)"| FICA',
            '    FICA -->|"Payment Medium File (SEPA/ACH/Wire)"| BANK',
        ])

        if include_tax:
            lines.append('    CI_BILL <-->|"Tax Determination / Calculation"| TAX')

        return "\n".join(lines)

    def generate_brim_sequence_mermaid(
        self,
        query: str = "",
        context: str = "",
    ) -> str:
        """
        Generate an end-to-end SAP BRIM call sequence diagram in Mermaid syntax.
        """
        lines: List[str] = [
            "sequenceDiagram",
            "    autonumber",
            "    actor Customer as Customer / Web Shop",
            "    participant APIGW as API Gateway",
            "    participant SOM as SAP SOM",
            "    participant CC as SAP CC",
            "    participant CI as SAP CI",
            "    participant FICA as SAP FI-CA",
            "    participant GL as S/4HANA Finance G/L",
            "",
            "    Customer->>APIGW: 1. Submit Subscription Order",
            "    APIGW->>SOM: 2. Forward Authenticated Order Request",
            "    SOM->>SOM: 3. Create Subscription Order & Trigger ODI",
            "    par Contract Provisioning",
            "        SOM->>CC: 4a. Provision Provider Contract & Charge Plans",
            "        SOM->>CI: 4b. Replicate Contract & Account Assignment",
            "    end",
            "    Note over CC: 5. External Usage Event arrives via Mediation",
            "    CC->>CC: 6. Rate & Charge Usage against Contract",
            "    CC->>CI: 7. Send Rated Billable Items (BITs)",
            "    Note over SOM,CI: 8. Optional recurring/one-off charges sent directly to CI",
            "    CI->>CI: 9. Execute Billing & Invoicing Mass Run",
            "    CI->>FICA: 10. Post Invoicing Documents & Open Items",
            "    Note over FICA: 11. Payments, Clearing & Dunning",
            "    FICA->>GL: 12. Transfer Aggregated Totals via Reconciliation Key",
        ]
        return "\n".join(lines)

    def generate_diagram(
        self,
        query: str = "",
        context: str = "",
    ) -> str:
        """
        Generate either an architecture flowchart or sequence diagram based on query intent.
        """
        combined = f"{query} {context}".lower()
        if "sequence" in combined:
            return self.generate_brim_sequence_mermaid(query, context)
        return self.generate_brim_architecture_mermaid(query, context)

    # -----------------------------------------------------------------------
    # Normalize provider output
    # -----------------------------------------------------------------------

    def _structure_vision_output(
        self,
        raw_text: str,
        meta: Dict[str, Any],
        user_query: str,
    ) -> Dict[str, Any]:
        """Normalize provider output and flag possible exposed credentials."""
        has_credentials, snippet = self.check_for_exposed_credentials(
            raw_text
        )

        mermaid_match = re.search(
            r"```mermaid\s*([\s\S]*?)```",
            raw_text,
            flags=re.IGNORECASE,
        )

        # Extract structured JSON block if returned by vision model
        structured = {}
        json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw_text)
        if json_match:
            try:
                structured = json.loads(json_match.group(1).strip())
            except Exception:
                structured = {}
        elif raw_text.strip().startswith("{") and raw_text.strip().endswith("}"):
            try:
                structured = json.loads(raw_text.strip())
            except Exception:
                structured = {}

        # Strip the trailing json block from formatted_text so user sees clean answer
        cleaned_text = re.sub(r"```(?:json)?\s*\{[\s\S]*?\}\s*```", "", raw_text).strip()
        if not cleaned_text:
            cleaned_text = raw_text

        formatted_text = cleaned_text

        if "### A. What I see" not in formatted_text:
            formatted_text = (
                "### A. What I see\n"
                f"Image dimensions: {meta.get('width')}x"
                f"{meta.get('height')} ({meta.get('format')}).\n\n"
                f"{cleaned_text}"
            )

        if has_credentials:
            alert = (
                "> [!CAUTION]\n"
                "> **Credential Exposure Warning:** The analysis output "
                "appears to contain a credential indicator "
                f"({snippet}). Redact the exposed value and rotate the "
                "credential if it is genuine.\n\n"
            )
            formatted_text = alert + formatted_text

        # Heuristic fallbacks if structured keys are not directly provided
        tcode = structured.get("transaction_code")
        if not tcode:
            m = re.search(r"\b([A-Z]{1,4}\d{1,4}[A-Z0-9]?)\b", user_query + " " + raw_text)
            if m and m.group(1).upper() not in {"HTTP", "JSON", "REST", "SOAP", "HTML", "UUID", "STEP", "POST", "GET", "PNG", "JPG"}:
                tcode = m.group(1).upper()

        msg_num = structured.get("message_class_and_number")
        if not msg_num:
            m = re.search(r"\b([A-Z0-9]{2,}\s*\d{3,4})\b", raw_text)
            if m:
                msg_num = m.group(1)

        err_text = structured.get("error_text")
        if not err_text:
            m = re.search(r"(?:error|message)\s*:\s*([^\n\.]+)", raw_text, re.IGNORECASE)
            if m:
                err_text = m.group(1).strip()

        is_unclear = meta.get("is_unclear", False) or any(k in raw_text.lower() for k in UNCLEAR_IMAGE_INDICATORS)
        readable = bool(structured.get("readable", not is_unclear))

        is_sap = bool(structured.get("is_sap", True))
        if "is_sap" not in structured:
            from backend.app.services.sap_classifier import sap_classifier
            is_sap, _ = sap_classifier.classify(user_query + " " + raw_text, has_attachment=True)

        screen_or_app = structured.get("screen_or_app") or (f"SAP GUI {tcode}" if tcode else "SAP Application Screen")
        module = structured.get("module") or ("SD" if tcode and tcode.startswith("V") else ("FI" if tcode and tcode.startswith("F") else ("Basis" if tcode and tcode.startswith("S") else None)))
        confidence = float(structured.get("confidence", 0.92 if readable else 0.1))

        return {
            "text": formatted_text,
            "is_unclear": not readable,
            "readable": readable,
            "is_sap": is_sap,
            "screen_or_app": screen_or_app,
            "transaction_code": tcode,
            "module": module,
            "message_class_and_number": msg_num,
            "error_text": err_text,
            "visible_fields_and_values": structured.get("visible_fields_and_values", {}),
            "confidence": confidence,
            "screen_type": "detected_by_vision",
            "detected_error": err_text,
            "has_credentials": has_credentials,
            "mermaid_code": mermaid_code,
        }

    def parse_sap_screenshot_structured(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
        user_query: str = "",
        conversation_context: str = "",
    ) -> Dict[str, Any]:
        """
        Parses an SAP screenshot using the vision pipeline and returns structured schema:
        is_sap (bool), screen_or_app (str), transaction_code (str or None),
        module (str or None), message_class_and_number (str or None),
        error_text (str or None), visible_fields_and_values (dict),
        readable (bool), confidence (float).
        """
        res = self.analyze_image_with_vision(
            image_bytes=image_bytes,
            mime_type=mime_type,
            user_query=user_query,
            conversation_context=conversation_context,
        )
        return {
            "is_sap": res.get("is_sap", True),
            "screen_or_app": res.get("screen_or_app", "SAP Screen"),
            "transaction_code": res.get("transaction_code"),
            "module": res.get("module"),
            "message_class_and_number": res.get("message_class_and_number"),
            "error_text": res.get("error_text"),
            "visible_fields_and_values": res.get("visible_fields_and_values", {}),
            "readable": res.get("readable", not res.get("is_unclear", False)),
            "confidence": res.get("confidence", 0.9 if not res.get("is_unclear") else 0.0),
            "text": res.get("text", ""),
            "screen_type": res.get("screen_type", "sap_gui"),
            "is_unclear": res.get("is_unclear", False),
            "has_credentials": res.get("has_credentials", False),
            "mermaid_code": res.get("mermaid_code"),
        }


# Shared service instance.
vision_service = VisionService()
