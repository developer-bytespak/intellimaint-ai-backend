from deepgram import DeepgramClient
from ..shared.config import get_settings
import httpx
import io

settings = get_settings()

class DeepgramService:
    """Service for Deepgram ASR and TTS operations"""
    
    def __init__(self):
        if not settings.deepgram_api_key:
            raise ValueError("DEEPGRAM_API_KEY environment variable is required")
        self.api_key = settings.deepgram_api_key
        self.client = DeepgramClient(api_key=self.api_key)
        self.base_url = "https://api.deepgram.com"
    
    async def transcribe_audio(self, audio_data: bytes, mimetype: str = "audio/wav") -> str:
        try:
            # Use Deepgram REST API directly for compatibility
            url = f"{self.base_url}/v1/listen"
            headers = {
                "Authorization": f"Token {self.api_key}",
                "Content-Type": mimetype
            }
            params = {
                "model": "nova-3",
                "language": "en",
                "punctuate": "true",
                "smart_format": "true",
                "remove_disfluencies": "true"
            }
            
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    params=params,
                    content=audio_data
                )
                response.raise_for_status()
                result = response.json()

                print(result)
                # Extract transcript
                if "results" in result and "channels" in result["results"]:
                    channels = result["results"]["channels"]
                    if len(channels) > 0 and "alternatives" in channels[0]:
                        alternatives = channels[0]["alternatives"]
                        if len(alternatives) > 0 and "transcript" in alternatives[0]:
                            return alternatives[0]["transcript"]
                
                return ""
        except Exception as e:
            raise Exception(f"Transcription failed: {str(e)}")
    
    async def synthesize_speech(self, text: str) -> bytes:
        try:
            # Use Deepgram REST API directly for TTS
            url = f"{self.base_url}/v1/speak"
            headers = {
                "Authorization": f"Token {self.api_key}",
                "Content-Type": "application/json"
            }
            params = {
                "model": "aura-2-thalia-en",
                "encoding": "linear16",
                "container": "wav"
            }
            data = {"text": text}
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    params=params,
                    json=data
                )
                response.raise_for_status()
                return response.content
        except Exception as e:
            raise Exception(f"TTS generation failed: {str(e)}")


# Global instance for DeepgramService
_deepgram_service = None

def get_deepgram_service() -> DeepgramService:
    """Get or create Deepgram service instance"""
    global _deepgram_service
    if _deepgram_service is None:
        _deepgram_service = DeepgramService()
    return _deepgram_service


# Function to transcribe audio using Deepgram
async def transcribe_audio(audio_data: bytes, mimetype: str = "audio/wav") -> str:
    """Transcribe audio using Deepgram"""
    service = get_deepgram_service()
    return await service.transcribe_audio(audio_data, mimetype)


# Function to synthesize speech using Deepgram
async def synthesize_speech(text: str) -> bytes:
    """Synthesize speech using Deepgram"""
    service = get_deepgram_service()
    return await service.synthesize_speech(text)
