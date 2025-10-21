"""Shared constants across services"""

SERVICE_URLS = {
    "orchestrator": "http://orchestrator:8000",
    "vision": "http://vision-service:8001",
    "rag": "http://rag-service:8002",
    "asr_tts": "http://asr-tts-service:8003",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
SUPPORTED_IMAGE_FORMATS = [".jpg", ".jpeg", ".png", ".webp"]
SUPPORTED_AUDIO_FORMATS = [".mp3", ".wav", ".m4a"]

