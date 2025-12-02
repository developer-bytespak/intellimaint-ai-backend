"""iFixit API configuration"""

import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# iFixit API Configuration
# Note: iFixit API does not require authentication, but you can optionally set an API key
# for higher rate limits if you have one
IFIXIT_API_BASE_URL = "https://www.ifixit.com/api/2.0"
IFIXIT_API_KEY = os.getenv("IFIXIT_API_KEY", "")  # Optional

# API Endpoints
ENDPOINTS = {
    "wikis": f"{IFIXIT_API_BASE_URL}/wikis",
    "devices": f"{IFIXIT_API_BASE_URL}/wikis/{{category}}/devices",
    "guides": f"{IFIXIT_API_BASE_URL}/guides",
    "guide_detail": f"{IFIXIT_API_BASE_URL}/guides/{{guide_id}}",
}

# Rate limiting configuration
RATE_LIMIT_REQUESTS_PER_SECOND = 2  # Conservative default
RATE_LIMIT_DELAY_SECONDS = 0.5  # Delay between requests in seconds

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF_FACTOR = 2  # Exponential backoff multiplier
RETRY_STATUS_CODES = [429, 500, 502, 503, 504]  # HTTP status codes to retry

# Request timeout
REQUEST_TIMEOUT = 30  # seconds

