import time
from app.services.asr_tts_service import transcribe_audio, synthesize_speech
# from app.services.rag_service import search_documents
import httpx
import json

class StreamService:

    def __init__(self):
        self.buffer = b""  # yahan audio chunks store honge temporary
        self.last_chunk_time = None  # last audio chunk ka time track karne ke liye
        self.silence_threshold = 1  # seconds of silence needed
        self.min_buffer_size = 1000  # minimum buffer size before processing (bytes)
        self.max_buffer_size = 500000  # maximum buffer size (500KB) - isse zyada hone par auto-process

    async def is_silence_detected(self) -> bool:
        """Check if silence detected - time-based approach"""
        if self.last_chunk_time is None:
            self.last_chunk_time = time.time()
            return False
        
        current_time = time.time()
        time_since_last_chunk = current_time - self.last_chunk_time
        
        # DEBUG print
        print(f"[Silence Check] Time since last: {time_since_last_chunk:.2f}s, Buffer: {len(self.buffer)} bytes")
        
        # Agar silence threshold se zyada time ho gaya ho aur buffer mein kuch data ho
        if time_since_last_chunk > self.silence_threshold and len(self.buffer) > 0:
            print(f"[Silence Check] SILENCE DETECTED!")
            return True
        
        return False

    async def transcribe_audio_buffer(self) -> str:
        """Audio buffer ko Deepgram STT ko bhej kar text mein convert karo"""
        try:
            if len(self.buffer) < self.min_buffer_size:
                print(f"Buffer too small: {len(self.buffer)} < {self.min_buffer_size}")
                return ""
            
            # Audio format detection - multiple formats try karte hain
            # Pehle WAV format try karo (agar proper WAV file hai)
            formats_to_try = [
                ("audio/wav", "WAV format"),
                ("audio/webm", "WebM format"),
                ("audio/raw", "Raw PCM format"),
                ("audio/opus", "Opus format"),
                ("audio/mp3", "MP3 format")
            ]
            
            last_error = None
            
            for mimetype, format_name in formats_to_try:
                try:
                    print(f"[STT] Trying {format_name} ({mimetype})...")
                    text = await transcribe_audio(self.buffer, mimetype=mimetype)
                    
                    if text and len(text.strip()) > 0:
                        print(f"[STT] Success with {format_name}: {text}")
                        return text
                    else:
                        print(f"[STT] Empty transcript with {format_name}, trying next format...")
                        
                except Exception as e:
                    error_msg = str(e)
                    last_error = error_msg
                    print(f"[STT] Failed with {format_name}: {error_msg}")
                    # Agar "400 Bad Request" hai aur format issue hai, next try karo
                    if "400" in error_msg or "Bad Request" in error_msg:
                        continue
                    # Agar authentication error ya rate limit, to break karo
                    elif "401" in error_msg or "403" in error_msg or "429" in error_msg:
                        raise e
            
            # Agar sab formats fail ho gaye
            if last_error:
                print(f"[STT] All formats failed. Last error: {last_error}")
            else:
                print(f"[STT] All formats returned empty transcript")
            
            return ""
            
        except Exception as e:
            error_msg = f"STT Error: {str(e)}"
            print(error_msg)
            return ""

    # async def get_rag_context(self, text: str) -> list:
    #     """User text se RAG se relevant context retrieve karo"""
    #     try:
    #         if not text or len(text.strip()) == 0:
    #             return []
            
    #         # RAG service se documents search karo
    #         result = await search_documents(text, top_k=5)
    #         documents = result.get("documents", [])
    #         print(f"RAG Context retrieved: {len(documents)} documents")
    #         return documents
    #     except Exception as e:
    #         print(f"RAG Error: {e}")
    #         return []

    async def call_llm(self, text: str) -> str:
        """LLM ko text aur RAG context ke saath call karo"""
        try:
            if not text or len(text.strip()) == 0:
                return "I didn't catch that. Could you please repeat?"
            
            # RAG context ko format karo
            context_text = ""
            # if rag_context:
            #     context_text = "\n\nRelevant Context:\n"
            #     for i, doc in enumerate(rag_context[:3], 1):  # Top 3 documents
                    # context_text += f"{i}. {doc}\n"
            
            # Simple LLM prompt (aap isko customize kar sakte hain)
            prompt = f"""You are a helpful assistant. Answer the user's question based on the provided context.

# {context_text} # comment out for now

User Question: {text}

Provide a clear and helpful response:"""
            
            # TODO: Yahan aap apna LLM API call kar sakte hain
            # Example: OpenAI, Anthropic, etc.
            # For now, simple echo response
            response = f"I heard: {text}"
            if context_text:
                response += "\n\nI found some relevant context to help answer your question."
            
            print(f"LLM Response: {response}")
            return response
            
        except Exception as e:
            print(f"LLM Error: {e}")
            return "I'm sorry, I encountered an error processing your request."

    async def text_to_audio(self, text: str) -> bytes:
        """Text ko Deepgram TTS se audio mein convert karo"""
        try:
            if not text or len(text.strip()) == 0:
                return b""
            
            # Deepgram TTS API call
            audio_data = await synthesize_speech(text)
            print(f"TTS generated: {len(audio_data)} bytes")
            return audio_data
        except Exception as e:
            print(f"TTS Error: {e}")
            return b""

    async def process_buffer(self) -> bytes | None:
        """Buffer ko process karke audio response return karo"""
        if len(self.buffer) == 0:
            print("Buffer is empty, nothing to process")
            return None
        
        print("Processing audio buffer...")
        
        # 1. STT: Audio buffer ko text mein convert karo
        text = await self.transcribe_audio_buffer()
        
        if text and len(text.strip()) > 0:
            # 2. LLM: Text ko LLM ko bhejo
            llm_response = await self.call_llm(text)
            
            # 3. TTS: LLM response ko audio mein convert karo
            audio_response = await self.text_to_audio(llm_response)
            
            # Buffer clear karo for next utterance
            self.buffer = b""
            self.last_chunk_time = None
            
            # Audio response return karo
            return audio_response
        else:
            print("No text transcribed, clearing buffer")
            self.buffer = b""
            self.last_chunk_time = None
            return None

    async def handle_stream(self, data: dict):
        # Text message aaya (stop signal ya koi aur message)
        if "text" in data:
            try:
                message = json.loads(data["text"])
                if message.get("type") == "stop" and message.get("action") == "end_stream":
                    print("Stop signal received! Processing accumulated buffer...")
                    return await self.process_buffer()
                else:
                    print(f"Unknown text message: {message}")
                    return None
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Error parsing text message: {e}, Raw data: {data.get('text')}")
                return None
        
        # Audio bytes aaya
        elif "bytes" in data:
            chunk = data["bytes"]
            print(f"Received AUDIO chunk: {len(chunk)} bytes")

            # Pehle silence check karo (previous chunk ke baad kitna time ho gaya)
            previous_chunk_time = self.last_chunk_time
            current_time = time.time()
            
            # Agar pehle se chunks aa rahe the, to time gap check karo
            if previous_chunk_time is not None:
                time_since_last = current_time - previous_chunk_time
                print(f"Time since last chunk: {time_since_last:.2f}s, Threshold: {self.silence_threshold}s")
                
                # Agar silence threshold cross ho gaya ho
                if time_since_last > self.silence_threshold and len(self.buffer) > 0:
                    print("Silence detected! Processing audio buffer...")
                    return await self.process_buffer()

            # buffer me add karo
            self.buffer += chunk
            self.last_chunk_time = current_time  # last chunk ka time update karo
            
            # DEBUG: Buffer status print karo
            print(f"Buffer size: {len(self.buffer)} bytes, Min required: {self.min_buffer_size}, Max: {self.max_buffer_size}")
            
            # Agar buffer max size se zyada ho gaya, to auto-process karo
            if len(self.buffer) > self.max_buffer_size:
                print(f"Buffer exceeded max size ({self.max_buffer_size} bytes)! Auto-processing...")
                return await self.process_buffer()

            return None  # Abhi kuch reply nahi bhejna (chunks collect ho rahe hain)

        else:
            print("Unknown data:", data)
            return None