"""Shared constants for AI service"""

# Since all services are now in the same container, we don't need external URLs
# Services can be called directly via imports

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
SUPPORTED_IMAGE_FORMATS = [".jpg", ".jpeg", ".png", ".webp"]
SUPPORTED_AUDIO_FORMATS = [".mp3", ".wav", ".m4a"]

