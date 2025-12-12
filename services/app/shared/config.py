import os
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv


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
        # Comma-separated list of allowed origins for CORS (e.g. https://app.onrender.com)
        raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
        self.allowed_origins = [o.strip() for o in raw.split(",") if o.strip()]
@lru_cache()
def get_settings():
    return Settings()

