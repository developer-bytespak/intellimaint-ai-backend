"""Vision service for image processing using OpenAI API."""

from __future__ import annotations
from dotenv import load_dotenv

load_dotenv()  # this reads .env and populates os.environ
import asyncio
import json
import os
import base64
from io import BytesIO
from typing import Any

try:
    from openai import OpenAI
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "The 'openai' package is required. Install via `pip install openai`."
    ) from exc

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "The 'Pillow' package is required. Install via `pip install Pillow`."
    ) from exc

MODEL_NAME = "gpt-4o"  # Can be changed to "gpt-4o-mini" for cheaper/faster processing

_api_key = os.getenv("OPENAI_API_KEY")
if not _api_key:
    raise RuntimeError("OPENAI_API_KEY environment variable is not set")

_client = OpenAI(api_key=_api_key)

async def _call_openai(prompt: str, image_bytes: bytes) -> str:
    """Internal helper to call OpenAI Vision API."""
    if not image_bytes:
        raise ValueError("Image bytes must be provided.")

    try:
        # Load and validate image
        image = Image.open(BytesIO(image_bytes))
        
        # Convert image to base64
        buffered = BytesIO()
        # Convert to RGB if necessary (for PNG with transparency)
        if image.mode in ('RGBA', 'P'):
            image = image.convert('RGB')
        image.save(buffered, format="JPEG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        # Create the message with image
        def _generate():
            return _client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{img_base64}",
                                    "detail": "auto"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=1000
            )
        
        response = await asyncio.to_thread(_generate)
        
        # Extract text from response
        if response.choices and response.choices[0].message.content:
            return response.choices[0].message.content.strip()
        
        raise RuntimeError("OpenAI response did not contain text output.")
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"OpenAI API request failed: {str(exc)}") from exc

async def detect_objects(image_data: bytes) -> dict[str, Any]:
    """Detect objects in image using OpenAI Vision API"""
    prompt = (
        "List key objects/components visible in this image as JSON. "
        "Preferred shape: {\"objects\": [...], \"notes\": \"...\"}."
    )
    text_output = await _call_openai(prompt, image_data)
    
    try:
        data = json.loads(text_output)
    except json.JSONDecodeError:
        return {"raw_text": text_output}

    if isinstance(data, dict):
        return data
    return {"items": data}

async def extract_text(image_data: bytes) -> str:
    """Extract text from image using OpenAI Vision API (OCR)"""
    prompt = (
        "Extract ONLY the text that is actually visible and readable in this image. "
        "Do NOT infer, guess, or add any text that is not clearly visible in the image. "
        "Do NOT include website URLs, email addresses, or any other information unless it is explicitly written and visible in the image. "
        "Return only the exact text that you can see in the image, one line per text element, preserving the order as it appears."
    )
    text_output = await _call_openai(prompt, image_data)
    return text_output

async def explain_image(image_data: bytes, question: str | None = None) -> str:
    """Generate image explanation using OpenAI Vision API"""
    if question:
        prompt = f"Answer the following question about this image: {question}"
    else:
        prompt = "Describe this image in detail, including visible objects, components, and context."
    
    explanation = await _call_openai(prompt, image_data)
    return explanation
