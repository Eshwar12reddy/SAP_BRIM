"""
Swappable provider adapter interface for generative image creation (Path B).
If disabled or unavailable, caller can fall back to Path A (deterministic SVG) or text-only.
"""

import abc
import logging
from typing import Optional
import httpx

from backend.app.config import settings

logger = logging.getLogger(__name__)


class BaseImageProviderAdapter(abc.ABC):
    @abc.abstractmethod
    async def generate_image(self, prompt: str) -> Optional[bytes]:
        """Generate image bytes from prompt. Returns None on failure or if disabled."""
        pass


class OpenAIImageAdapter(BaseImageProviderAdapter):
    """Adapter for OpenAI Images API (DALL-E 3 / DALL-E 2)."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.OPENAI_API_KEY or settings.LLM_API_KEY
        self.model = model or settings.IMAGE_GENERATION_MODEL or "dall-e-3"

    async def generate_image(self, prompt: str) -> Optional[bytes]:
        if not self.api_key:
            logger.warning("OpenAIImageAdapter: No API key provided for image generation.")
            return None

        url = "https://api.openai.com/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024",
            "response_format": "b64_json",
        }

        try:
            async with httpx.AsyncClient(timeout=settings.VISUAL_GENERATION_TIMEOUT_SECONDS) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code != 200:
                    logger.error(f"OpenAI Image API returned status {resp.status_code}: {resp.text[:200]}")
                    return None
                data = resp.json()
                import base64
                b64_data = data["data"][0].get("b64_json")
                if b64_data:
                    return base64.b64decode(b64_data)
                url_data = data["data"][0].get("url")
                if url_data:
                    img_resp = await client.get(url_data)
                    if img_resp.status_code == 200:
                        return img_resp.content
        except Exception as e:
            logger.error(f"OpenAI image generation error: {e}")
            return None

        return None


class MockImageAdapter(BaseImageProviderAdapter):
    """Mock adapter for testing without external network calls."""

    async def generate_image(self, prompt: str) -> Optional[bytes]:
        # Return a simple 1x1 or small valid PNG banner
        # 1x1 transparent PNG bytes
        return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"


def get_image_provider_adapter() -> BaseImageProviderAdapter:
    provider = (settings.IMAGE_GENERATION_PROVIDER or "openai").lower()
    if provider == "mock":
        return MockImageAdapter()
    return OpenAIImageAdapter()
