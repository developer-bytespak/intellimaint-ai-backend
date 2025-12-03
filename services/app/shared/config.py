import os
from functools import lru_cache
<<<<<<< HEAD
from pathlib import Path
from dotenv import load_dotenv


services_dir = Path(__file__).parent.parent.parent
env_path = services_dir / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    # Try loading from current directory or parent directories
    load_dotenv()
=======
>>>>>>> u-vlm

class Settings:
    def __init__(self):
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.database_url = os.getenv("DATABASE_URL")
        self.redis_url = os.getenv("REDIS_URL")
<<<<<<< HEAD
        self.deepgram_api_key = os.getenv("DEEPGRAM_API_KEY")
        print(f"Deepgram API Key: {self.deepgram_api_key}")  # Debugging line
=======
>>>>>>> u-vlm

@lru_cache()
def get_settings():
    return Settings()

