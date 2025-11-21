"""iFixit API configuration"""

import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
# Try multiple locations (project root and gateway directory)
project_root = Path(__file__).parent.parent.parent
env_paths = [
    project_root / '.env',
    project_root / 'gateway' / '.env',
]
for env_path in env_paths:
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
        break
else:
    # If no .env file found, try loading from current directory
    load_dotenv(override=False)

# iFixit API Configuration
# Note: iFixit API does not require authentication, but you can optionally set an API key
# for higher rate limits if you have one
IFIXIT_API_BASE_URL = "https://www.ifixit.com/api/2.0"
IFIXIT_API_KEY = os.getenv("IFIXIT_API_KEY", "")  # Optional

# API Endpoints
ENDPOINTS = {
    "categories": f"{IFIXIT_API_BASE_URL}/categories",
    "devices": f"{IFIXIT_API_BASE_URL}/categories/{{category}}/devices",
    "guides": f"{IFIXIT_API_BASE_URL}/guides",
    "guide_detail": f"{IFIXIT_API_BASE_URL}/guides/{{guide_id}}",
}

# Rate limiting configuration (override via environment)
RATE_LIMIT_REQUESTS_PER_SECOND = float(os.getenv("IFIXIT_RATE_LIMIT_RPS", "2"))
RATE_LIMIT_DELAY_SECONDS = (
    1.0 / RATE_LIMIT_REQUESTS_PER_SECOND if RATE_LIMIT_REQUESTS_PER_SECOND > 0 else 0.5
)

# Retry configuration
MAX_RETRIES = int(os.getenv("IFIXIT_MAX_RETRIES", "3"))
RETRY_BACKOFF_FACTOR = float(os.getenv("IFIXIT_RETRY_BACKOFF_FACTOR", "2"))  # Exponential backoff multiplier
RETRY_STATUS_CODES = [429, 500, 502, 503, 504]  # HTTP status codes to retry

# Request timeout (reduced from 30 to 15 seconds for faster failure detection)
REQUEST_TIMEOUT = int(os.getenv("IFIXIT_REQUEST_TIMEOUT", "15"))  # seconds

# Pagination defaults
DEFAULT_PAGE_SIZE = int(os.getenv("IFIXIT_DEFAULT_PAGE_SIZE", "100"))
MAX_PAGE_SIZE = int(os.getenv("IFIXIT_MAX_PAGE_SIZE", "200"))

