from deepgram import DeepgramClient
from ..shared.config import get_settings
import httpx
import re
from typing import List

settings = get_settings()

class DeepgramService:
    """Service for Deepgram ASR and TTS operations"""
    
    def __init__(self):
        if not settings.deepgram_api_key:
            raise ValueError("DEEPGRAM_API_KEY environment variable is required")
        self.api_key = settings.deepgram_api_key
        self.client = DeepgramClient(api_key=self.api_key)
        self.base_url = "https://api.deepgram.com"
    
    async def transcribe_audio(self, audio_data: bytes, mimetype: str = "audio/wav", sample_rate: int = None) -> str:
        try:
            # Audio buffer validation
            if not audio_data or len(audio_data) < 100:
                raise ValueError(f"Audio buffer too small: {len(audio_data)} bytes")
            
            print(f"[Deepgram] Sending audio: {len(audio_data)} bytes, mimetype: {mimetype}")
            
            # Use Deepgram REST API directly
            url = f"{self.base_url}/v1/listen"
            # FORCE proper mimetype for WebM Opus
            if mimetype.startswith("audio/webm"):
                mimetype = "audio/webm;codecs=opus"

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
            
            # For raw PCM audio, specify encoding
            if mimetype in ["audio/raw", "audio/pcm"]:
                params["encoding"] = "linear16"
                params["sample_rate"] = sample_rate if sample_rate else 16000
                params["channels"] = 1
            
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    params=params,
                    content=audio_data
                )
                
                # Error handling
                if response.status_code != 200:
                    error_detail = f"Status: {response.status_code}"
                    try:
                        error_json = response.json()
                        error_detail += f", Response: {error_json}"
                        print(f"[Deepgram Error] {error_detail}")
                    except:
                        error_text = response.text[:500]
                        error_detail += f", Response: {error_text}"
                        print(f"[Deepgram Error] {error_detail}")
                    
                    raise Exception(f"Transcription failed: {error_detail}")
                
                result = response.json()

                # Extract transcript
                if "results" in result and "channels" in result["results"]:
                    channels = result["results"]["channels"]
                    if len(channels) > 0 and "alternatives" in channels[0]:
                        alternatives = channels[0]["alternatives"]
                        if len(alternatives) > 0 and "transcript" in alternatives[0]:
                            return alternatives[0]["transcript"]
                
                return ""
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text[:500] if hasattr(e.response, 'text') else str(e)}"
            print(f"[Deepgram HTTP Error] {error_msg}")
            raise Exception(f"Transcription failed: {error_msg}")
        except Exception as e:
            error_msg = f"Transcription failed: {str(e)}"
            print(f"[Deepgram Exception] {error_msg}")
            raise Exception(error_msg)
        
        
    def split_text_into_chunks(self, text: str, max_chars: int = 200) -> List[str]:
        """
        Split text into chunks at sentence boundaries, respecting max_chars limit.
        """
        # Remove extra whitespace
        text = " ".join(text.split())
        
        # If text is already short enough, return as-is
        if len(text) <= max_chars:
            return [text]
        
        # Split by sentence endings (., !, ?)
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            # If single sentence exceeds limit, split by words
            if len(sentence) > max_chars:
                words = sentence.split()
                for word in words:
                    if len(current_chunk) + len(word) + 1 <= max_chars:
                        current_chunk += word + " "
                    else:
                        if current_chunk.strip():
                            chunks.append(current_chunk.strip())
                        current_chunk = word + " "
            else:
                # Try to add sentence to current chunk
                test_chunk = current_chunk + sentence + " "
                if len(test_chunk) <= max_chars:
                    current_chunk = test_chunk
                else:
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence + " "
        
        # Add remaining chunk
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks if chunks else [text]
    
    async def _synthesize_single_chunk(self, text: str) -> bytes:
        """
        Synthesize a single chunk of text (≤200 chars).
        """
        try:
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
            print(f"[Deepgram TTS Error] Chunk failed: {str(e)}")
            raise
    
    def _concatenate_wav_files(self, wav_files: List[bytes]) -> bytes:
        """
        Concatenate multiple WAV files into one.
        Strips WAV headers from all files except the first.
        """
        if not wav_files:
            return b""
        
        if len(wav_files) == 1:
            return wav_files[0]
        
        # Start with first file (includes WAV header)
        result = bytearray(wav_files[0])
        
        # Append subsequent files WITHOUT their WAV headers (44 bytes)
        for wav_bytes in wav_files[1:]:
            if len(wav_bytes) > 44:
                result.extend(wav_bytes[44:])  # Skip WAV header
        
        return bytes(result)
    
    async def synthesize_speech(self, text: str) -> bytes:
        """
        Synthesize speech with automatic chunking for long text.
        Returns concatenated audio bytes.
        """
        try:
            # Split text into chunks
            chunks = self.split_text_into_chunks(text, max_chars=200)
            
            print(f"[Deepgram TTS] Text length: {len(text)} chars")
            print(f"[Deepgram TTS] Split into {len(chunks)} chunk(s)")
            
            # Generate audio for each chunk
            audio_chunks = []
            for i, chunk in enumerate(chunks, 1):
                print(f"[Deepgram TTS] Processing chunk {i}/{len(chunks)}: '{chunk[:50]}...'")
                audio_bytes = await self._synthesize_single_chunk(chunk)
                audio_chunks.append(audio_bytes)
                print(f"[Deepgram TTS] Chunk {i} generated: {len(audio_bytes)} bytes")
            
            # Concatenate all audio chunks
            final_audio = self._concatenate_wav_files(audio_chunks)
            print(f"[Deepgram TTS] Final audio: {len(final_audio)} bytes")
            
            return final_audio
            
        except Exception as e:
            print(f"[Deepgram TTS Error] {str(e)}")
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
