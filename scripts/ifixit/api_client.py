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
            with attempt:
                self._rate_limit(delay_override)
                logger.debug("Requesting %s params=%s", url, params)
                response = self.session.get(url, params=params, timeout=timeout or self.timeout)

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
            page_params = {**base_params, "limit": size, "offset": offset}
            response = self._request_with_retry(url, params=page_params, delay_override=delay_override)
            payload = response.json()
            items, total = self._extract_results(payload)

            logger.debug(
                "Fetched page %s from %s offset=%s size=%s received=%s total=%s",
                page_index,
                url,
                offset,
                size,
                len(items),
                total,
            )

            if not items:
                break

            yield items

            page_index += 1
            offset += size

            if len(items) < size:
                break
            if max_pages is not None and page_index >= max_pages:
                break
            if total is not None and offset >= total:
                break

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

        logger.info("Fetching guides from %s with params=%s", url, params)

        try:
            if paginate:
                collected: List[Dict[str, Any]] = []
                for page in self.paginate(url, params=params, page_size=page_size, max_pages=max_pages):
                    collected.extend(page)
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

