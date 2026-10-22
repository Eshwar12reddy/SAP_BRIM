import re
import logging
import time
import threading
import urllib.parse
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

import requests
from tavily import TavilyClient, InvalidAPIKeyError, MissingAPIKeyError

from backend.app.config import settings

logger = logging.getLogger(__name__)


class TavilyAuthenticationError(RuntimeError):
    """Raised when Tavily has no configured key or rejects its API key."""


class TavilySearchError(RuntimeError):
    """Raised for retryable Tavily transport or service errors."""

# Strict approved SAP domain allowlist
APPROVED_SAP_DOMAINS = [
    "help.sap.com",
    "community.sap.com",
    "blogs.sap.com",
    "learning.sap.com",
    "support.sap.com",
    "answers.sap.com",
    "sap.com"
]

# Curated SAP BRIM references supplied for search prioritization. Search still
# runs for each user question; these URLs are trusted targets, not static answer
# evidence. Results returned from a configured path receive its priority.
SAP_SOURCE_URLS = [
    {"name": "SAP Help Portal - BRIM", "url": "https://help.sap.com/docs/BRIM", "priority": 1},
    {"name": "SAP BRIM Product Documentation", "url": "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/a03da85e7c96487aac46d431799bebdf/c918bf4f27f44f71888040e6ae3add31.html", "priority": 1},
    {"name": "SAP Subscription Order Management", "url": "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/a03da85e7c96487aac46d431799bebdf/08934ac6a2a546e1bec39eff3b8a14e1.html", "priority": 1},
    {"name": "SAP Convergent Charging", "url": "https://help.sap.com/docs/r/product/Convergent_Charging/latest", "priority": 1},
    {"name": "SAP BRIM Integration Guides", "url": "https://help.sap.com/docs/PRODUCT_ID/7587f50ad2ca4f888b2fb5507faccae4/8d62944ef3e548efbac1bd4908c71819.html", "priority": 1},
    {"name": "SAP Learning - Usage to Cash", "url": "https://learning.sap.com/learning-journeys/sap-billing-and-revenue-innovation-management-brim-implementing-usage-to-cash", "priority": 2},
    {"name": "SAP BRIM Community", "url": "https://community.sap.com/topics/billing-revenue-innovation-management", "priority": 3},
]

class TimeoutHTTPAdapter(requests.adapters.HTTPAdapter):
    """Enforces configurable connect and read timeouts on underlying HTTP requests."""

    def __init__(self, connect_timeout: float = 3.0, read_timeout: float = 8.0, *args, **kwargs):
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        super().__init__(*args, **kwargs)

    def send(self, request, **kwargs):
        timeout = kwargs.get("timeout")
        if timeout is None or isinstance(timeout, (int, float)):
            kwargs["timeout"] = (
                self.connect_timeout,
                min(float(timeout) if timeout else self.read_timeout, self.read_timeout),
            )
        return super().send(request, **kwargs)


class WebSearchService:
    """
    Authoritative SAP web search through the configured Tavily API.
    """

    def __init__(self):
        self.api_key = settings.WEB_SEARCH_API_KEY.strip()
        self.client: Optional[TavilyClient] = None
        self._timing_state = threading.local()

        if self.api_key:
            try:
                session = requests.Session()
                adapter = TimeoutHTTPAdapter(
                    connect_timeout=settings.TAVILY_CONNECT_TIMEOUT_SECONDS,
                    read_timeout=settings.TAVILY_READ_TIMEOUT_SECONDS,
                )
                session.mount("https://", adapter)
                session.mount("http://", adapter)
                self.client = TavilyClient(api_key=self.api_key, session=session)
            except Exception as e:
                logger.warning("Failed to initialize TavilyClient (%s).", type(e).__name__)
                self.client = None

    @staticmethod
    def _is_approved_sap_domain(url: str) -> bool:
        """Enforces hard domain restriction on approved SAP domains."""
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        return parsed.scheme == "https" and any(
            host == domain or host.endswith("." + domain)
            for domain in APPROVED_SAP_DOMAINS
        )

    @staticmethod
    def _extract_authority_tier(url: str, domain: str) -> int:
        """
        Determines authority tier:
        Tier 1: Official SAP Product Documentation & Support Notes (help.sap.com, learning.sap.com, support.sap.com)
        Tier 2: SAP Community & Expert Blogs (community.sap.com, blogs.sap.com, answers.sap.com)
        Tier 3: Other verified SAP web resources
        """
        target = f"{url} {domain}".lower()
        if "help.sap.com" in target or "learning.sap.com" in target or "support.sap.com" in target:
            return 1
        elif "community.sap.com" in target or "blogs.sap.com" in target or "answers.sap.com" in target:
            return 2
        return 3

    @staticmethod
    def _configured_source_priority(url: str) -> Optional[int]:
        """Return configured priority when a result matches a curated SAP path."""
        candidate = urllib.parse.urlparse(url)
        candidate_host = (candidate.hostname or "").lower()
        candidate_path = candidate.path.rstrip("/").lower()
        for source in SAP_SOURCE_URLS:
            configured = urllib.parse.urlparse(source["url"])
            configured_host = (configured.hostname or "").lower()
            configured_path = configured.path.rstrip("/").lower()
            if candidate_host == configured_host and (
                candidate_path == configured_path
                or candidate_path.startswith(configured_path + "/")
            ):
                return int(source["priority"])
        return None

    @staticmethod
    def _clean_text(value: Any) -> str:
        """Cleans HTML tags, multiple spaces, and escape sequences."""
        if not value:
            return ""
        text = str(value)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @property
    def api_key_configured(self) -> bool:
        return bool(self.api_key and self.client)

    def reset_request_timing(self) -> None:
        self._timing_state.elapsed_ms = 0.0

    @property
    def request_elapsed_ms(self) -> float:
        return float(getattr(self._timing_state, "elapsed_ms", 0.0))

    @staticmethod
    def sanitize_query_for_search(query: str) -> str:
        """
        Strips private data (emails, passwords, tokens, API keys, customer names/numbers)
        before submitting to external web search providers.
        """
        clean = query
        # 1. Strip email addresses
        clean = re.sub(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "[REDACTED_EMAIL]", clean)
        # 2. Strip passwords, tokens, API keys, secrets
        clean = re.sub(r"(?i)\b(password|passwd|pwd|token|bearer|api[_-]?key|secret)\s*[:=]\s*['\"]?[^\s'\"]+", "[REDACTED_SECRET]", clean)
        clean = re.sub(r"(?i)-u\s+[a-zA-Z0-9_\-\.]+:[^\s'\"]+", "-u [REDACTED_AUTH]", clean)
        # 3. Strip customer names / sensitive identifiers
        clean = re.sub(r"(?i)\b(customer\s*(?:name|id)?|account\s*(?:number|id)?|client\s*id)\s*[:=]\s*['\"]?[a-zA-Z0-9_\-\.]{3,}", r"\1 [REDACTED_ID]", clean)
        return clean.strip()

    @staticmethod
    def _sanitize_web_snippet(text: str) -> str:
        """Neutralizes prompt injection directives embedded in external web content."""
        if not text:
            return ""
        injection_patterns = [
            r"(?i)ignore\s+(?:all\s+)?previous\s+instructions",
            r"(?i)system\s+prompt\s+override",
            r"(?i)you\s+are\s+now\s+(?:an?\s+)?(?:ai|assistant|unrestricted)",
            r"(?i)disregard\s+(?:all\s+)?prior\s+guidance",
        ]
        sanitized = text
        for p in injection_patterns:
            sanitized = re.sub(p, "[UNTRUSTED_INSTRUCTION_REMOVED]", sanitized)
        return sanitized

    def search_sap_authoritative(
        self,
        query: str,
        max_results: Optional[int] = None,
        deadline: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Searches the live web using Tavily with strict SAP domain restrictions.
        Sanitizes private data, handles retries, and neutralizes web injection attempts.
        Enforces connect/read timeouts and strict overall deadline.
        """
        limit = min(max_results or settings.TAVILY_MAX_RESULTS, 5)
        if not self.api_key_configured:
            raise TavilyAuthenticationError("Tavily API key is missing or the client could not be initialized.")

        sanitized_query = self.sanitize_query_for_search(query)
        search_query = f"SAP {sanitized_query}" if not sanitized_query.lower().startswith("sap") else sanitized_query

        search_started = time.perf_counter()
        result_count = 0
        outcome = "error"
        timeout_count = 0
        response = None
        max_retries = getattr(settings, "TAVILY_MAX_RETRIES", 1)
        overall_deadline = deadline if deadline is not None else (time.perf_counter() + settings.TAVILY_OVERALL_DEADLINE_SECONDS)

        for attempt in range(max_retries + 1):
            remaining = overall_deadline - time.perf_counter()
            if remaining <= 0:
                outcome = "deadline_exceeded"
                logger.warning(
                    "Tavily web search overall deadline (%.1fs) exceeded before attempt %d.",
                    settings.TAVILY_OVERALL_DEADLINE_SECONDS,
                    attempt + 1,
                )
                break

            current_timeout = min(float(settings.TAVILY_TIMEOUT_SECONDS), max(1.0, remaining))
            try:
                response = self.client.search(
                    query=search_query,
                    search_depth="fast",
                    max_results=limit,
                    include_answer=False,
                    include_raw_content=False,
                    include_domains=APPROVED_SAP_DOMAINS,
                    include_domains_mode="restrict",
                    timeout=current_timeout,
                )
                result_count = len(response.get("results", [])) if isinstance(response, dict) and isinstance(response.get("results", []), list) else 0
                outcome = "success"
                break
            except (InvalidAPIKeyError, MissingAPIKeyError) as exc:
                outcome = "authentication_error"
                logger.error("Tavily rejected the configured API key (%s).", type(exc).__name__)
                raise TavilyAuthenticationError("Tavily API key is invalid, expired, or missing.") from exc
            except Exception as exc:
                is_timeout = isinstance(exc, (TimeoutError, requests.exceptions.Timeout)) or "timeout" in type(exc).__name__.lower()
                if is_timeout:
                    timeout_count += 1
                outcome = type(exc).__name__
                remaining_after = overall_deadline - time.perf_counter()
                if attempt < max_retries and remaining_after > 1.0:
                    backoff = min(0.5 * (attempt + 1), remaining_after - 0.5)
                    logger.info(
                        "Tavily attempt %d failed (%s, timeout_count=%d); retrying in %.2fs (remaining=%.2fs)...",
                        attempt + 1, outcome, timeout_count, backoff, remaining_after
                    )
                    time.sleep(backoff)
                    continue
                logger.warning(
                    "Tavily search failed after attempt %d (outcome=%s, timeout_count=%d, elapsed=%.2fms).",
                    attempt + 1, outcome, timeout_count, (time.perf_counter() - search_started) * 1000
                )
                raise TavilySearchError(f"Tavily search failed: {outcome}") from exc
            finally:
                elapsed_ms = (time.perf_counter() - search_started) * 1000
                self._timing_state.elapsed_ms = self.request_elapsed_ms + elapsed_ms

        logger.info(
            "pipeline_timing stage=tavily_search elapsed_ms=%.2f result_count=%d outcome=%s timeout_count=%d",
            self.request_elapsed_ms,
            result_count,
            outcome,
            timeout_count,
        )

        raw_results = response.get("results", []) if isinstance(response, dict) else []
        if not isinstance(raw_results, list):
            logger.warning("Tavily returned malformed results; the results field was not a list.")
            return []
        results: List[Dict[str, Any]] = []
        seen_urls = set()

        for item in raw_results:
            url = str(item.get("url", "")).strip()
            if not url or url in seen_urls:
                continue

            # Hard domain restriction check
            if not self._is_approved_sap_domain(url):
                continue

            seen_urls.add(url)

            raw_title = self._clean_text(item.get("title", "")) or "SAP Official Documentation"
            raw_snippet = self._clean_text(item.get("content", "")) or "No preview available."
            title = self._sanitize_web_snippet(raw_title)
            snippet = self._sanitize_web_snippet(raw_snippet)
            extracted_content = snippet

            # Determine specific domain
            host = (urllib.parse.urlparse(url).hostname or "").lower()
            if host == "help.sap.com" or host.endswith(".help.sap.com"):
                domain = "help.sap.com"
            elif host == "blogs.sap.com" or host.endswith(".blogs.sap.com"):
                domain = "blogs.sap.com"
            elif host == "community.sap.com" or host.endswith(".community.sap.com"):
                domain = "community.sap.com"
            elif host == "learning.sap.com" or host.endswith(".learning.sap.com"):
                domain = "learning.sap.com"
            elif host == "support.sap.com" or host.endswith(".support.sap.com"):
                domain = "support.sap.com"
            elif host == "answers.sap.com" or host.endswith(".answers.sap.com"):
                domain = "answers.sap.com"
            else:
                domain = "sap.com"

            authority_tier = self._extract_authority_tier(url, domain)

            results.append({
                "source_id": f"web_{len(results)+1}_{domain}",
                "title": title,
                "url": url,
                "domain": domain,
                "snippet": snippet,
                "chunk_text": f"{title}\n{extracted_content}",
                "authority_tier": authority_tier,
                "source_priority": self._configured_source_priority(url),
                "source_type": "web",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            })

            if len(results) >= limit:
                break

        return results


web_search_service = WebSearchService()
