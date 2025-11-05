"""ASR/TTS service using Deepgram SDK"""

from deepgram import DeepgramClient, ReadV1Request, SpeakV1Model
from ..shared.config import get_settings
import io

settings = get_settings()

class DeepgramService:
    """Service for Deepgram ASR and TTS operations"""
    
    def __init__(self):
        if not settings.deepgram_api_key:
            raise ValueError("DEEPGRAM_API_KEY environment variable is required")
        self.client = DeepgramClient(api_key=settings.deepgram_api_key)
    
    async def transcribe_audio(self, audio_data: bytes, mimetype: str = "audio/wav") -> str:
        """
        Transcribe audio using Deepgram ASR
        
        Args:
            audio_data: Audio file bytes
            mimetype: MIME type of the audio file (e.g., 'audio/wav', 'audio/mp3')
            
        Returns:
            Transcribed text string
        """
        try:
            # Create request payload for Deepgram SDK v5.x
            request = ReadV1Request(
                buffer=audio_data,
                mimetype=mimetype
            )
            
            # Configure options
            options = {
                "model": "nova-2",
                "language": "en",
                "punctuate": True,
            }
            
            response = self.client.read.v("1").transcribe_file(request, options)
            
            if response.status_code != 200:
                raise Exception(f"Deepgram API error: {response.status_code}")
            
            # Extract transcript from response
            if (response.response_json and 
                "results" in response.response_json and
                "channels" in response.response_json["results"] and
                len(response.response_json["results"]["channels"]) > 0):
                
                transcript = (
                    response.response_json["results"]["channels"][0]
                    .get("alternatives", [{}])[0]
                    .get("transcript", "")
                )
                return transcript
            
            return ""
        except Exception as e:
            raise Exception(f"Transcription failed: {str(e)}")
    
    async def synthesize_speech(self, text: str) -> bytes:
        
        try:
            # Configure TTS options for Deepgram SDK v5.x
            options = {
                "model": SpeakV1Model.AURA_2_THALIA_EN,
                "encoding": "linear16",
                "container": "wav"
            }
            
            request = {
                "text": text
            }
            
            response = self.client.speak.v("1").stream(request, options)
            
            if response.status_code != 200:
                raise Exception(f"Deepgram TTS API error: {response.status_code}")
            
            # Read audio bytes from response
            audio_bytes = b""
            if hasattr(response, 'stream'):
                audio_bytes = response.stream.read()
            elif hasattr(response, 'content'):
                audio_bytes = response.content
            
            return audio_bytes
        except Exception as e:
            raise Exception(f"TTS generation failed: {str(e)}")


# Global instance
_deepgram_service = None

def get_deepgram_service() -> DeepgramService:
    """Get or create Deepgram service instance"""
    global _deepgram_service
    if _deepgram_service is None:
        _deepgram_service = DeepgramService()
    return _deepgram_service


async def transcribe_audio(audio_data: bytes, mimetype: str = "audio/wav") -> str:
    """Transcribe audio using Deepgram"""
    service = get_deepgram_service()
    return await service.transcribe_audio(audio_data, mimetype)


async def synthesize_speech(text: str) -> bytes:
    """Synthesize speech using Deepgram"""
    service = get_deepgram_service()
    return await service.synthesize_speech(text)

