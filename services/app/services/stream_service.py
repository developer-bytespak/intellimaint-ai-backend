import time
from app.services.asr_tts_service import transcribe_audio, synthesize_speech
import httpx
import json
import filetype

class StreamService:

    def __init__(self, default_format: str = "audio/webm"):
        self.buffer = b""  # yahan audio chunks store honge temporary
        self.last_chunk_time = None  # last audio chunk ka time track karne ke liye
        self.silence_threshold = 1.5  # seconds of silence needed (increased to 1.5s)
        self.min_buffer_size = 8000  # minimum buffer size before processing (8KB)
        self.max_buffer_size = 500000  # maximum buffer size (500KB)
        self.audio_format = default_format  # Default format
        self.format_detected = False  # Track if format has been set by client
        self.working_format = None  # Track which format worked successfully
        self.is_first_chunk = True  # Track first chunk for validation
        self.chunk_count = 0  # Track number of chunks received

    async def is_silence_detected(self) -> bool:
        """Check if silence detected - time-based approach"""
        if self.last_chunk_time is None:
            self.last_chunk_time = time.time()
            return False
        
        current_time = time.time()
        time_since_last_chunk = current_time - self.last_chunk_time
        
        print(f"[Silence Check] Time since last: {time_since_last_chunk:.2f}s, Buffer: {len(self.buffer)} bytes")
        
        # Agar silence threshold se zyada time ho gaya ho aur buffer mein kuch data ho
        if time_since_last_chunk > self.silence_threshold and len(self.buffer) > 0:
            print(f"[Silence Check] SILENCE DETECTED!")
            return True
        
        return False

    def validate_webm_header(self, audio_data: bytes) -> bool:
        """WebM file ka header validate karo"""
        if len(audio_data) < 4:
            return False
        
        # WebM EBML header check: 1A 45 DF A3
        if audio_data[:4] == b'\x1a\x45\xdf\xa3':
            print("[Validation] ✓ Valid WebM EBML header found")
            return True
        
        print(f"[Validation] ✗ Invalid WebM header")
        print(f"[Validation] First 32 bytes (hex): {audio_data[:32].hex()}")
        return False

    def detect_audio_format(self, audio_data: bytes) -> str:
        """Detect the audio format from the buffer using multiple methods."""
        if len(audio_data) < 4:
            print("[Format Detection] Buffer too small for detection")
            return None
        
        # Debug info
        print(f"[Format Detection] Buffer size: {len(audio_data)} bytes")
        print(f"[Format Detection] First 32 bytes (hex): {audio_data[:32].hex()}")
        
        # Method 1: Check for magic bytes
        if len(audio_data) >= 4:
            # WebM/Matroska magic bytes: 1A 45 DF A3
            if audio_data[:4] == b'\x1a\x45\xdf\xa3':
                if self.validate_webm_header(audio_data):
                    print("[Format Detection] ✓ Detected WebM via magic bytes")
                    return "audio/webm"
            
            # WAV files start with RIFF header
            if audio_data[:4] == b'RIFF':
                print("[Format Detection] ✓ Detected WAV via magic bytes")
                return "audio/wav"
            
            # OGG/Opus files start with OggS
            if audio_data[:4] == b'OggS':
                print("[Format Detection] ✓ Detected OGG/Opus via magic bytes")
                return "audio/ogg"
            
            # MP3 files
            if audio_data[:3] == b'ID3' or (audio_data[0] == 0xFF and (audio_data[1] & 0xE0) == 0xE0):
                print("[Format Detection] ✓ Detected MP3 via magic bytes")
                return "audio/mp3"
        
        # Method 2: Try filetype library
        try:
            kind = filetype.guess(audio_data)
            if kind is not None:
                print(f"[Format Detection] filetype library: {kind.mime}")
                if kind.mime == "video/webm":
                    return "audio/webm"
                elif kind.mime in ["audio/webm", "audio/wav", "audio/ogg", "audio/mpeg"]:
                    return kind.mime
        except Exception as e:
            print(f"[Format Detection] filetype error: {e}")
        
        # Method 3: Working format from previous success
        if self.working_format:
            print(f"[Format Detection] Using working format: {self.working_format}")
            return self.working_format
        
        # Method 4: Client-specified format
        if self.format_detected and self.audio_format:
            print(f"[Format Detection] Using client format: {self.audio_format}")
            return self.audio_format
        
        # Could not detect
        print("[Format Detection] ✗ Could not detect format")
        return None

    def set_audio_format(self, format_str: str):
        """Set audio format explicitly from client"""
        valid_formats = ["audio/webm", "audio/wav", "audio/ogg", "audio/opus", "audio/mpeg", "audio/mp3"]
        
        # Normalize
        if format_str == "audio/opus":
            format_str = "audio/ogg"
        
        if format_str in valid_formats:
            self.audio_format = format_str
            self.format_detected = True
            print(f"[Format] ✓ Client set format to: {format_str}")
        else:
            print(f"[Format] ✗ Invalid format {format_str}")

    async def transcribe_audio_buffer(self) -> str:
        """Audio buffer ko Deepgram STT ko bhej kar text mein convert karo"""
        try:
            # Buffer size check
            if len(self.buffer) < self.min_buffer_size:
                print(f"[STT] ✗ Buffer too small: {len(self.buffer)} < {self.min_buffer_size}")
                return ""
            
            print(f"[STT] Processing buffer: {len(self.buffer)} bytes from {self.chunk_count} chunks")
            
            # Detect format
            detected_format = self.detect_audio_format(self.buffer)
            
            # Build formats to try
            formats_to_try = []
            
            if detected_format:
                formats_to_try.append(detected_format)
            
            if self.working_format and self.working_format not in formats_to_try:
                formats_to_try.append(self.working_format)
            
            if self.audio_format not in formats_to_try:
                formats_to_try.append(self.audio_format)
            
            # Fallback formats
            fallback = ["audio/webm", "audio/ogg", "audio/wav"]
            for fmt in fallback:
                if fmt not in formats_to_try:
                    formats_to_try.append(fmt)
            
            print(f"[STT] Formats to try: {formats_to_try}")
            
            # Try each format
            last_error = None
            for format_to_try in formats_to_try:
                try:
                    print(f"[STT] Trying format: {format_to_try}")
                    text = await transcribe_audio(self.buffer, mimetype=format_to_try)
                    
                    if text and len(text.strip()) > 0:
                        print(f"[STT] ✓ SUCCESS with {format_to_try}")
                        print(f"[STT] Transcribed: '{text[:100]}...'")
                        self.working_format = format_to_try  # Remember successful format
                        return text
                    else:
                        print(f"[STT] Empty response with {format_to_try}")
                        
                except Exception as e:
                    last_error = str(e)
                    print(f"[STT] ✗ Failed with {format_to_try}: {last_error}")
                    continue
            
            # All formats failed
            print(f"[STT] ✗✗✗ ALL FORMATS FAILED ✗✗✗")
            print(f"[STT] Buffer: {len(self.buffer)} bytes, Chunks: {self.chunk_count}")
            print(f"[STT] First 64 bytes: {self.buffer[:64].hex()}")
            print(f"[STT] Last error: {last_error}")
            return ""
                
        except Exception as e:
            print(f"[STT] ✗ Unexpected Error: {str(e)}")
            import traceback
            print(f"[STT] Traceback: {traceback.format_exc()}")
            return ""

    async def call_llm(self, text: str) -> str:
        """LLM ko text bhejo"""
        try:
            if not text or len(text.strip()) == 0:
                return "I didn't catch that. Could you please repeat?"
            
            # Simple echo for now
            response = f"I heard: {text}"
            print(f"[LLM] Response: {response}")
            return response
            
        except Exception as e:
            print(f"[LLM] Error: {e}")
            return "I'm sorry, I encountered an error processing your request."

    async def text_to_audio(self, text: str) -> bytes:
        """Text ko Deepgram TTS se audio mein convert karo"""
        try:
            if not text or len(text.strip()) == 0:
                return b""
            
            audio_data = await synthesize_speech(text)
            print(f"[TTS] Generated: {len(audio_data)} bytes")
            return audio_data
        except Exception as e:
            print(f"[TTS] Error: {e}")
            return b""

    async def process_buffer(self) -> bytes | None:
        """Buffer ko process karke audio response return karo"""
        if len(self.buffer) == 0:
            print("[Process] Buffer is empty, nothing to process")
            return None
        
        print(f"[Process] Processing buffer: {len(self.buffer)} bytes, {self.chunk_count} chunks")
        
        # 1. STT
        text = await self.transcribe_audio_buffer()
        
        if text and len(text.strip()) > 0:
            # 2. LLM
            llm_response = await self.call_llm(text)
            
            # 3. TTS
            audio_response = await self.text_to_audio(llm_response)
            
            # Clear buffer
            self.buffer = b""
            self.last_chunk_time = None
            self.is_first_chunk = True
            self.chunk_count = 0
            
            return audio_response
        else:
            print("[Process] No text transcribed, clearing buffer")
            self.buffer = b""
            self.last_chunk_time = None
            self.is_first_chunk = True
            self.chunk_count = 0
            return None

    async def handle_stream(self, data: dict):
        # Text message (stop signal, config, etc.)
        if "text" in data:
            try:
                message = json.loads(data["text"])
                
                # Format config
                if message.get("type") == "config" and "format" in message:
                    format_str = message.get("format")
                    self.set_audio_format(format_str)
                    return None
                
                # Stop signal
                elif message.get("type") == "stop" and message.get("action") == "end_stream":
                    print("=" * 60)
                    print("🛑 STOP SIGNAL RECEIVED - Processing buffer...")
                    print("=" * 60)
                    return await self.process_buffer()
                else:
                    print(f"[Stream] Unknown text message: {message}")
                    return None
                    
            except (json.JSONDecodeError, KeyError) as e:
                print(f"[Stream] Error parsing text: {e}, Data: {data.get('text')}")
                return None
        
        # Audio bytes
        elif "bytes" in data:
            chunk = data["bytes"]
            self.chunk_count += 1
            
            print(f"[Stream] Chunk #{self.chunk_count}: {len(chunk)} bytes")
            
            # First chunk validation
            if self.is_first_chunk and self.audio_format == "audio/webm":
                if not self.validate_webm_header(chunk):
                    print("[Stream] ⚠️ WARNING: First chunk has invalid WebM header!")
                self.is_first_chunk = False

            # Silence detection
            previous_chunk_time = self.last_chunk_time
            current_time = time.time()
            
            if previous_chunk_time is not None:
                time_since_last = current_time - previous_chunk_time
                
                if time_since_last > self.silence_threshold and len(self.buffer) >= self.min_buffer_size:
                    print("=" * 60)
                    print("🔇 SILENCE DETECTED - Processing buffer...")
                    print("=" * 60)
                    return await self.process_buffer()

            # Add to buffer
            self.buffer += chunk
            self.last_chunk_time = current_time
            
            print(f"[Stream] Total buffer: {len(self.buffer)} bytes (min: {self.min_buffer_size}, max: {self.max_buffer_size})")
            
            # Auto-process if buffer too large
            if len(self.buffer) > self.max_buffer_size:
                print("=" * 60)
                print("📦 BUFFER FULL - Auto-processing...")
                print("=" * 60)
                return await self.process_buffer()

            return None

        else:
            print(f"[Stream] Unknown data: {data}")
            return None