"""iFixit API client with rate limiting and retry logic"""

import time
import requests
from typing import Optional, Dict, Any, List
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_result,
    retry_if_exception_type
)
import logging

from .config import (
    IFIXIT_API_KEY,
    ENDPOINTS,
    RATE_LIMIT_DELAY_SECONDS,
    MAX_RETRIES,
    RETRY_STATUS_CODES,
    REQUEST_TIMEOUT
)

logger = logging.getLogger(__name__)


class iFixitAPIClient:
    """Client for interacting with iFixit API with rate limiting and retry logic"""
    
    def __init__(self, api_key: Optional[str] = None, delay: float = RATE_LIMIT_DELAY_SECONDS):
        """
        Initialize iFixit API client
        
        Args:
            api_key: iFixit API key (optional, not required - API works without auth)
            delay: Delay between requests in seconds (default from config)
        """
        self.api_key = api_key or IFIXIT_API_KEY
        self.delay = delay
        self.last_request_time = 0
        self.session = requests.Session()
        
        # Set headers (API key is optional - iFixit API works without authentication)
        self.session.headers.update({
            "Content-Type": "application/json"
        })
        if self.api_key:
            self.session.headers.update({
                "Authorization": f"Bearer {self.api_key}"
            })
    
    def _rate_limit(self):
        """Enforce rate limiting between requests"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        
        if time_since_last_request < self.delay:
            sleep_time = self.delay - time_since_last_request
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _should_retry(self, response: requests.Response) -> bool:
        """Check if request should be retried based on status code"""
        return response.status_code in RETRY_STATUS_CODES
    
    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((requests.exceptions.RequestException,))
    )
    def _make_request(self, url: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
        """
        Make HTTP request with rate limiting and retry logic
        
        Args:
            url: API endpoint URL
            params: Query parameters
            
        Returns:
            Response object
            
        Raises:
            requests.exceptions.RequestException: If request fails after retries
        """
        self._rate_limit()
        
        try:
            response = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            if self._should_retry(response):
                logger.warning(f"Retrying request to {url} due to status {response.status_code}")
                raise
            logger.error(f"HTTP error for {url}: {e}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error for {url}: {e}")
            raise
    
    def get_wikis(self) -> List[Dict[str, Any]]:
        """
        Get all wikis (categories) from iFixit
        
        Returns:
            List of wiki dictionaries
        """
        url = ENDPOINTS["wikis"]
        logger.info(f"Fetching wikis from {url}")
        
        try:
            response = self._make_request(url)
            data = response.json()
            
            # Handle different response formats
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return data.get("data", data.get("results", []))
            return []
        except Exception as e:
            logger.error(f"Error fetching wikis: {e}")
            return []
    
    def get_devices(self, category: str) -> List[Dict[str, Any]]:
        """
        Get all devices for a specific category
        
        Args:
            category: Category/wiki name
            
        Returns:
            List of device dictionaries
        """
        url = ENDPOINTS["devices"].format(category=category)
        logger.info(f"Fetching devices for category '{category}' from {url}")
        
        try:
            response = self._make_request(url)
            data = response.json()
            
            # Handle different response formats
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return data.get("data", data.get("results", []))
            return []
        except Exception as e:
            logger.error(f"Error fetching devices for category '{category}': {e}")
            return []
    
    def get_guides(self, device_id: Optional[str] = None, device_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get guides for a device
        
        Args:
            device_id: Device ID (optional)
            device_name: Device name/namespace (optional)
            
        Returns:
            List of guide dictionaries
        """
        url = ENDPOINTS["guides"]
        params = {}
        
        if device_id:
            params["device"] = device_id
        elif device_name:
            params["device"] = device_name
        
        logger.info(f"Fetching guides from {url} with params: {params}")
        
        try:
            response = self._make_request(url, params=params if params else None)
            data = response.json()
            
            # Handle different response formats
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return data.get("data", data.get("results", []))
            return []
        except Exception as e:
            logger.error(f"Error fetching guides: {e}")
            return []
    
    def get_guide_detail(self, guide_id: int) -> Optional[Dict[str, Any]]:
        """
        Get detailed information for a specific guide
        
        Args:
            guide_id: Guide ID
            
        Returns:
            Guide detail dictionary or None if not found
        """
        url = ENDPOINTS["guide_detail"].format(guide_id=guide_id)
        logger.debug(f"Fetching guide detail for guide_id {guide_id}")
        
        try:
            response = self._make_request(url)
            data = response.json()
            
            # Handle different response formats
            if isinstance(data, dict):
                return data.get("data", data)
            return data
        except Exception as e:
            logger.error(f"Error fetching guide detail for guide_id {guide_id}: {e}")
            return None

