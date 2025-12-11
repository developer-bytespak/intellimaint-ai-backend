"""iFixit API client with configurable rate limiting, retries, and pagination helpers."""

import logging
import time
from typing import Any, Dict, Generator, List, Optional, Tuple

import requests
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import (
    DEFAULT_PAGE_SIZE,
    ENDPOINTS,
    IFIXIT_API_KEY,
    MAX_PAGE_SIZE,
    MAX_RETRIES,
    RATE_LIMIT_DELAY_SECONDS,
    REQUEST_TIMEOUT,
    RETRY_BACKOFF_FACTOR,
    RETRY_STATUS_CODES,
)

logger = logging.getLogger(__name__)


class RetryableHTTPError(requests.exceptions.HTTPError):
    """Raised when a response should be retried based on status code."""


class iFixitAPIClient:
    """Client for interacting with iFixit API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        delay: float = RATE_LIMIT_DELAY_SECONDS,
        timeout: int = REQUEST_TIMEOUT,
        max_retries: int = MAX_RETRIES,
    ):
        """
        Initialize the client.

        Args:
            api_key: Optional API key for elevated limits.
            delay: Base delay (seconds) enforced between requests.
            timeout: Request timeout in seconds.
            max_retries: Maximum retries for transient failures.
        """
        self.api_key = api_key or IFIXIT_API_KEY
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.last_request_time = 0.0

        self.session = requests.Session()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        self.session.headers.update(headers)

    # ------------------------------------------------------------------ #
    # Rate limiting
    # ------------------------------------------------------------------ #
    def _rate_limit(self, delay_override: Optional[float] = None) -> None:
        delay = delay_override if delay_override is not None else self.delay
        if delay <= 0:
            return

        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < delay:
            sleep_time = delay - elapsed
            logger.debug("Rate limiting: sleeping %.3fs", sleep_time)
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    # ------------------------------------------------------------------ #
    # Request handling
    # ------------------------------------------------------------------ #
    def _request_with_retry(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        delay_override: Optional[float] = None,
        timeout: Optional[int] = None,
    ) -> requests.Response:
        """Execute an HTTP GET with retries and logging."""

        retryer = Retrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=RETRY_BACKOFF_FACTOR, min=1, max=30),
            retry=retry_if_exception_type((requests.exceptions.RequestException, RetryableHTTPError)),
            reraise=True,
        )

        for attempt in retryer:
            # Check for global shutdown flag before each request
            try:
                from scripts.ifixit.collect_ifixit_data import _shutdown_requested_global
                if _shutdown_requested_global:
                    logger.warning("Shutdown requested, aborting request to %s", url)
                    raise KeyboardInterrupt("Shutdown requested")
            except ImportError:
                pass  # If import fails, continue (might be called from different context)
                
            with attempt:
                self._rate_limit(delay_override)
                logger.debug("Requesting %s params=%s (attempt %d/%d)", url, params, attempt.retry_state.attempt_number, self.max_retries)
                try:
                    # Use shorter timeout for faster interrupt response
                    request_timeout = min(timeout or self.timeout, 5)  # Max 5 seconds per request
                    response = self.session.get(url, params=params, timeout=request_timeout)
                except requests.exceptions.Timeout as exc:
                    logger.warning("Request timeout after %s seconds for %s", timeout or self.timeout, url)
                    raise
                except requests.exceptions.RequestException as exc:
                    logger.warning("Request error for %s: %s", url, exc)
                    raise

                if self._should_retry(response):
                    logger.warning(
                        "Retryable status %s for %s params=%s",
                        response.status_code,
                        url,
                        params,
                    )
                    raise RetryableHTTPError(f"Retryable response {response.status_code}", response=response)

                try:
                    response.raise_for_status()
                except requests.exceptions.HTTPError as exc:
                    logger.error("HTTP error for %s params=%s: %s", url, params, exc)
                    raise

                return response

        # Should not reach here because Retrying with reraise will raise.
        raise RuntimeError("Exhausted retries without returning a response.")

    @staticmethod
    def _should_retry(response: requests.Response) -> bool:
        return response.status_code in RETRY_STATUS_CODES

    # ------------------------------------------------------------------ #
    # Pagination helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_results(payload: Any) -> Tuple[List[Any], Optional[int]]:
        """
        Normalize iFixit response payloads into (items, total) tuples.
        """
        if isinstance(payload, list):
            return payload, None

        if isinstance(payload, dict):
            for key in ("results", "data", "items"):
                if key in payload and isinstance(payload[key], list):
                    total = payload.get("total") or payload.get("count") or payload.get("totalResults")
                    return payload[key], total

            if payload and all(value is None for value in payload.values()):
                items = [{"title": key, "namespace": key} for key in payload.keys()]
                return items, len(items)

        return [], None

    def paginate(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        page_size: Optional[int] = None,
        max_pages: Optional[int] = None,
        delay_override: Optional[float] = None,
    ) -> Generator[List[Any], None, None]:
        """
        Generic pagination generator for iFixit endpoints.
        """
        size = min(page_size or DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE)
        base_params = dict(params or {})
        offset = int(base_params.pop("offset", 0))

        page_index = 0
        while True:
            # Check for global shutdown flag
            from scripts.ifixit.collect_ifixit_data import _shutdown_requested_global
            if _shutdown_requested_global:
                logger.warning("Shutdown requested, stopping pagination")
                break
                
            logger.info("Fetching page %d from %s (offset=%d, limit=%d, params=%s)", page_index + 1, url, offset, size, base_params)
            page_params = {**base_params, "limit": size, "offset": offset}
            try:
                response = self._request_with_retry(url, params=page_params, delay_override=delay_override)
                payload = response.json()
                items, total = self._extract_results(payload)

                logger.info(
                    "Fetched page %d: received %d items (total=%s)",
                    page_index + 1,
                    len(items),
                    total if total is not None else "unknown",
                )
            except Exception as exc:
                logger.error("Error fetching page %d: %s", page_index + 1, exc)
                break

            if not items:
                break

            yield items

            page_index += 1
            offset += size

            if len(items) < size:
                logger.info("Received fewer items than page size (%d < %d), stopping pagination", len(items), size)
                break
            if max_pages is not None and page_index >= max_pages:
                logger.warning("Reached max_pages limit (%d), stopping pagination. There may be more items.", max_pages)
                break
            if total is not None and offset >= total:
                logger.info("Reached total items (%d), stopping pagination", total)
                break
            
            # Safety check: if we've fetched more than 10,000 items without a total count, warn but continue
            # The script will stop naturally when it receives fewer items than page size (end of results)
            if total is None and offset >= 10000 and offset % 10000 == 0:
                logger.warning("Fetched %d+ items without total count. Continuing to fetch all guides...", offset)
                # Don't break - continue fetching until we get an empty response or fewer items than page size

    # ------------------------------------------------------------------ #
    # API methods
    # ------------------------------------------------------------------ #
    def get_categories(self) -> Dict[str, Any]:
        url = ENDPOINTS["categories"]
        logger.info("Fetching categories from %s", url)

        try:
            response = self._request_with_retry(url)
            data = response.json()
            if isinstance(data, dict):
                return data
            return {}
        except Exception as exc:
            logger.error("Error fetching categories: %s", exc)
            return {}

    def get_wikis(self) -> List[Dict[str, Any]]:
        categories = self.get_categories()
        return self._flatten_categories(categories)

    def _flatten_categories(self, categories: Dict[str, Any], path: str = "") -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for key, value in categories.items():
            current_path = f"{path}/{key}" if path else key
            if value is None:
                result.append({"namespace": current_path, "title": key, "path": current_path})
            elif isinstance(value, dict):
                result.append(
                    {
                        "namespace": current_path,
                        "title": key,
                        "path": current_path,
                        "type": "category",
                    }
                )
                result.extend(self._flatten_categories(value, current_path))
        return result

    def get_devices(self, category: str) -> List[Dict[str, Any]]:
        url = ENDPOINTS["devices"].format(category=category)
        logger.info("Fetching devices for category '%s' from %s", category, url)

        try:
            response = self._request_with_retry(url)
            data = response.json()

            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                if not data or all(v is None for v in data.values()):
                    return [{"title": key, "namespace": key} for key in data.keys()]
                return data.get("data", data.get("results", []))
            return []
        except Exception as exc:
            logger.error("Error fetching devices for category '%s': %s", category, exc)
            return []

    def get_guides(
        self,
        device_id: Optional[str] = None,
        device_name: Optional[str] = None,
        category: Optional[str] = None,
        paginate: bool = False,
        page_size: Optional[int] = None,
        max_pages: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        url = ENDPOINTS["guides"]
        params: Dict[str, Any] = {}

        if device_id:
            params["device"] = device_id
        elif device_name:
            params["device"] = device_name
        
        if category:
            params["category"] = category

        if params:
            logger.info("Fetching guides from %s with params=%s", url, params)
        else:
            logger.warning("Fetching guides from %s WITHOUT device filter - this will fetch ALL guides!", url)

        try:
            if paginate:
                collected: List[Dict[str, Any]] = []
                page_count = 0
                for page in self.paginate(url, params=params, page_size=page_size, max_pages=max_pages):
                    collected.extend(page)
                    page_count += 1
                    # Log progress every 5 pages or on first page
                    if page_count == 1 or page_count % 5 == 0:
                        logger.info("Progress: Collected %d guides so far (from %d pages)...", len(collected), page_count)
                logger.info("✅ Completed fetching: %d total guides from %d pages", len(collected), page_count)
                return collected

            response = self._request_with_retry(url, params=params or None)
            data = response.json()

            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("data", data.get("results", []))
            return []
        except Exception as exc:
            logger.error("Error fetching guides: %s", exc)
            return []

    def get_guide_detail(self, guide_id: int) -> Optional[Dict[str, Any]]:
        url = ENDPOINTS["guide_detail"].format(guide_id=guide_id)
        logger.debug("Fetching guide detail for guide_id=%s", guide_id)

        try:
            response = self._request_with_retry(url)
            data = response.json()

            if isinstance(data, dict):
                return data.get("data", data)
            return data
        except Exception as exc:
            logger.error("Error fetching guide detail for guide_id %s: %s", guide_id, exc)
            return None

