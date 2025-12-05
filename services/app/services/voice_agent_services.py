# from deepgram import DeepgramClient
# from dotenv import load_dotenv
# import os
# import httpx

# # Load .env file to fetch API key
# load_dotenv()

# # Deepgram API Key directly set karte hain
# dg_api_key = os.getenv("DEEPGRAM_API_KEY")
# dg_client = DeepgramClient(api_key=dg_api_key)
# base_url = "https://api.deepgram.com"

# async def process_audio(audio_file_path):
#     try:
#         # Deepgram ke Speech-to-Text API ka use karke audio ko transcribe karenge
#         # Read the audio file
#         with open(audio_file_path, "rb") as audio_file:
#             audio_data = audio_file.read()
        
#         # Use Deepgram REST API directly
#         url = f"{base_url}/v1/listen"
#         headers = {
#             "Authorization": f"Token {dg_api_key}",
#             "Content-Type": "audio/wav"  # Adjust based on file type
#         }
#         params = {
#             "model": "nova-3",
#             "language": "en",
#             "punctuate": "true",
#             "smart_format": "true"
#         }
        
#         async with httpx.AsyncClient(timeout=300.0) as client:
#             response = await client.post(
#                 url,
#                 headers=headers,
#                 params=params,
#                 content=audio_data
#             )
#             response.raise_for_status()
#             result = response.json()
            
#             # Extract transcript
#             if "results" in result and "channels" in result["results"]:
#                 channels = result["results"]["channels"]
#                 if len(channels) > 0 and "alternatives" in channels[0]:
#                     alternatives = channels[0]["alternatives"]
#                     if len(alternatives) > 0 and "transcript" in alternatives[0]:
#                         return alternatives[0]["transcript"]
        
#         return None
#     except Exception as e:
#         print(f"Error in processing audio: {e}")
#         return None

# async def text_to_speech(text):
#     try:
#         # Deepgram TTS API ke liye URL
#         url = f"{base_url}/v1/synthesize"
        
#         # Request parameters (for TTS)
#         params = {
#             "model": "nova-3",
#             "language": "en",
#             "voice": "en_us_male",  # You can change the voice here
#             "text": text,
#         }
        
#         headers = {
#             "Authorization": f"Token {dg_api_key}",
#             "Content-Type": "application/json",
#         }

#         async with httpx.AsyncClient() as client:
#             # Make the request to the TTS endpoint
#             response = await client.post(url, headers=headers, params=params)
#             response.raise_for_status()
            
#             # Audio content (mp3 or wav format)
#             audio_data = response.content
#             return audio_data
        
#     except Exception as e:
#         print(f"Error in generating speech: {e}")
#         return None
