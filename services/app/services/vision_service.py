"""Vision service for image processing using Google Gemini API."""

from __future__ import annotations
from dotenv import load_dotenv

load_dotenv()  # this reads .env and populates os.environ
import asyncio
import json
import os
from io import BytesIO
from typing import Any

try:
    import google.generativeai as genai
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "The 'google-generativeai' package is required. Install via `pip install google-generativeai`."
    ) from exc

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "The 'Pillow' package is required. Install via `pip install Pillow`."
    ) from exc

MODEL_NAME = "gemini-2.5-flash"  # Can be changed to "gemini-2.0-flash-exp" or "gemini-2.5-flash-lite" if available

_api_key = os.getenv("GEMINI_API_KEY")
if not _api_key:
    raise RuntimeError("GEMINI_API_KEY environment variable is not set")

genai.configure(api_key=_api_key)

async def _call_gemini(prompt: str, image_bytes: bytes) -> str:
    """Internal helper to call Gemini Vision API."""
    if not image_bytes:
        raise ValueError("Image bytes must be provided.")

    try:
        # Load image from bytes
        image = Image.open(BytesIO(image_bytes))
        
        # Initialize the model
        model = genai.GenerativeModel(MODEL_NAME)
        
        # Generate content with image and prompt (run in thread pool for async)
        def _generate():
            return model.generate_content([prompt, image])
        
        response = await asyncio.to_thread(_generate)
        
        # Extract text from response
        if response.text:
            return response.text.strip()
        
        # Fallback: try to get text from candidates
        if response.candidates:
            for candidate in response.candidates:
                if candidate.content and candidate.content.parts:
                    text_parts = []
                    for part in candidate.content.parts:
                        if hasattr(part, 'text') and part.text:
                            text_parts.append(part.text.strip())
                    if text_parts:
                        return "\n".join(text_parts)
        
        raise RuntimeError("Gemini response did not contain text output.")
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"Gemini API request failed: {str(exc)}") from exc

async def detect_objects(image_data: bytes) -> dict[str, Any]:
    """Detect objects in image using Gemini Vision API"""
    prompt = (
        "List key objects/components visible in this image as JSON. "
        "Preferred shape: {\"objects\": [...], \"notes\": \"...\"}."
    )
    text_output = await _call_gemini(prompt, image_data)
    
    try:
        data = json.loads(text_output)
    except json.JSONDecodeError:
        return {"raw_text": text_output}

    if isinstance(data, dict):
        return data
    return {"items": data}

async def extract_text(image_data: bytes) -> str:
    """Extract text from image using Gemini Vision API (OCR)"""
    prompt = (
        "Extract ONLY the text that is actually visible and readable in this image. "
        "Do NOT infer, guess, or add any text that is not clearly visible in the image. "
        "Do NOT include website URLs, email addresses, or any other information unless it is explicitly written and visible in the image. "
        "Return only the exact text that you can see in the image, one line per text element, preserving the order as it appears."
    )
    text_output = await _call_gemini(prompt, image_data)
    return text_output

async def explain_image(image_data: bytes, question: str | None = None) -> str:
    """Generate image explanation using Gemini Vision API"""
    if question:
        prompt = f"Answer the following question about this image: {question}"
    else:
        prompt = "Describe this image in detail, including visible objects, components, and context."
    
    explanation = await _call_gemini(prompt, image_data)
    return explanation
