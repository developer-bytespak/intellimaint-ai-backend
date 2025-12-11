from deepgram import DeepgramClient
from ..shared.config import get_settings
import httpx
import io

# Optional import for audio conversion
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
     # 🔥 Force ffmpeg path (works on Render)
    AudioSegment.converter = "/usr/bin/ffmpeg"
    AudioSegment.ffprobe = "/usr/bin/ffprobe"
except ImportError:
    PYDUB_AVAILABLE = False
    print("[Warning] pydub not available. Audio conversion will be disabled. Install pydub and ffmpeg for WebM support.")

settings = get_settings()

class DeepgramService:
    """Service for Deepgram ASR and TTS operations"""
    
    def __init__(self):
        if not settings.deepgram_api_key:
            raise ValueError("DEEPGRAM_API_KEY environment variable is required")
        self.api_key = settings.deepgram_api_key
        self.client = DeepgramClient(api_key=self.api_key)
        self.base_url = "https://api.deepgram.com"
    
    def convert_audio_to_wav(self, audio_data: bytes, input_format: str) -> bytes:
        """Convert audio from various formats to WAV format"""
        if not PYDUB_AVAILABLE:
            raise ImportError("pydub is not available. Please install pydub and ffmpeg for audio conversion.")
        
        try:
            print(f"[Audio Conversion] Converting {input_format} to WAV...")
            
            # Create AudioSegment from bytes
            audio_segment = AudioSegment.from_file(
                io.BytesIO(audio_data),
                format=input_format.replace("audio/", "")
            )
            
            # Export to WAV format
            wav_buffer = io.BytesIO()
            audio_segment.export(wav_buffer, format="wav")
            wav_data = wav_buffer.getvalue()
            
            print(f"[Audio Conversion] Converted {len(audio_data)} bytes to {len(wav_data)} bytes WAV")
            return wav_data
        except Exception as e:
            print(f"[Audio Conversion] Error converting audio: {e}")
            raise Exception(f"Audio conversion failed: {str(e)}")
    
    async def transcribe_audio(self, audio_data: bytes, mimetype: str = "audio/wav", sample_rate: int = None) -> str:
        try:
            # Audio buffer validation
            if not audio_data or len(audio_data) < 100:
                raise ValueError(f"Audio buffer too small: {len(audio_data)} bytes")
            
            # Convert WebM/Opus to WAV for better Deepgram compatibility
            # WebM chunks may not form a valid file when concatenated
            formats_to_convert = ["audio/webm", "audio/opus"]
            if mimetype in formats_to_convert:
                try:
                    print(f"[Deepgram] Converting {mimetype} to WAV for better compatibility...")
                    audio_data = self.convert_audio_to_wav(audio_data, mimetype)
                    mimetype = "audio/wav"
                except Exception as conv_error:
                    print(f"[Deepgram] Conversion failed, trying original format: {conv_error}")
                    # Continue with original format if conversion fails
            
            print(f"[Deepgram] Sending audio: {len(audio_data)} bytes, mimetype: {mimetype}")
            
            # Use Deepgram REST API directly for compatibility
            url = f"{self.base_url}/v1/listen"
            headers = {
                "Authorization": f"Token {self.api_key}",
                "Content-Type": mimetype
            }
            
            # Params ko flexible banate hain - encoding auto-detect ke liye
            params = {
                "model": "nova-3",
                "language": "en",
                "punctuate": "true",
                "smart_format": "true",
                "remove_disfluencies": "true"
            }
            
            # Agar mimetype raw hai, to encoding specify karo
            if mimetype in ["audio/raw", "audio/pcm"]:
                params["encoding"] = "linear16"
                params["sample_rate"] = sample_rate if sample_rate else 16000  # Use provided or default
                params["channels"] = 1
            
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    params=params,
                    content=audio_data
                )
                
                # Detailed error handling
                if response.status_code != 200:
                    error_detail = f"Status: {response.status_code}"
                    try:
                        error_json = response.json()
                        error_detail += f", Response: {error_json}"
                        print(f"[Deepgram Error] {error_detail}")
                    except:
                        error_text = response.text[:500]  # First 500 chars
                        error_detail += f", Response: {error_text}"
                        print(f"[Deepgram Error] {error_detail}")
                    
                    raise Exception(f"Transcription failed: {error_detail}")
                
                result = response.json()

                # print(f"[Deepgram Response] {result}")
                # Extract transcript
                if "results" in result and "channels" in result["results"]:
                    channels = result["results"]["channels"]
                    if len(channels) > 0 and "alternatives" in channels[0]:
                        alternatives = channels[0]["alternatives"]
                        if len(alternatives) > 0 and "transcript" in alternatives[0]:
                            return alternatives[0]["transcript"]
                
                return ""
        except httpx.HTTPStatusError as e:
            # HTTP error details capture karo
            error_msg = f"HTTP {e.response.status_code}: {e.response.text[:500] if hasattr(e.response, 'text') else str(e)}"
            print(f"[Deepgram HTTP Error] {error_msg}")
            raise Exception(f"Transcription failed: {error_msg}")
        except Exception as e:
            error_msg = f"Transcription failed: {str(e)}"
            print(f"[Deepgram Exception] {error_msg}")
            raise Exception(error_msg)
    
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
async def transcribe_audio(audio_data: bytes, mimetype: str = "audio/wav", sample_rate: int = None) -> str:
    """Transcribe audio using Deepgram"""
    service = get_deepgram_service()
    return await service.transcribe_audio(audio_data, mimetype, sample_rate)


# Function to synthesize speech using Deepgram
async def synthesize_speech(text: str) -> bytes:
    """Synthesize speech using Deepgram"""
    service = get_deepgram_service()
    return await service.synthesize_speech(text)
