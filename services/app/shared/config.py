import os
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from services directory (if it exists)
# This allows environment variables to be set either via .env file or system environment
services_dir = Path(__file__).parent.parent.parent
env_path = services_dir / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    # Try loading from current directory or parent directories
    load_dotenv()

class Settings:
    def __init__(self):
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.database_url = os.getenv("DATABASE_URL")
        self.redis_url = os.getenv("REDIS_URL")
        self.deepgram_api_key = os.getenv("DEEPGRAM_API_KEY")

@lru_cache()
def get_settings():
    return Settings()

