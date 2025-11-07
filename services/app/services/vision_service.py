"""Vision service for image processing using GPT-4o Vision API."""

from __future__ import annotations
from dotenv import load_dotenv

load_dotenv()  # this reads .env and populates os.environ
import base64
import importlib
import json
import os
from typing import Any

try:
    _openai = importlib.import_module("openai")
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "The 'openai' package is required. Install via `pip install openai`."
    ) from exc

AsyncOpenAI = getattr(_openai, "AsyncOpenAI")

MODEL_NAME = "gpt-4o-mini"

_api_key = os.getenv("OPENAI_API_KEY")
if not _api_key:
    raise RuntimeError("OPENAI_API_KEY environment variable is not set")

_client = AsyncOpenAI(api_key=_api_key)

async def _call_gpt4o(prompt: str, image_bytes: bytes) -> str:
    """Internal helper to call GPT-4o Vision API."""
    if not image_bytes:
        raise ValueError("Image bytes must be provided.")

    encoded_image = base64.b64encode(image_bytes).decode("utf-8")
    data_uri = f"data:image/jpeg;base64,{encoded_image}"

    try:
        response = await _client.responses.create(
            model=MODEL_NAME,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_image",
                            "image_url": data_uri,
                        },
                    ],
                }
            ],
            max_output_tokens=600,
        )
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("GPT-4o API request failed") from exc

    response_data = response.model_dump()
    output_text = (response_data.get("output_text") or "").strip()
    if output_text:
        return output_text

    text_parts: list[str] = []
    for item in response_data.get("output", []):
        for block in item.get("content", []):
            if block.get("type") == "output_text":
                text = (block.get("text") or "").strip()
                if text:
                    text_parts.append(text)

    if text_parts:
        return "\n".join(text_parts)

    raise RuntimeError("GPT-4o response did not contain text output.")

async def detect_objects(image_data: bytes) -> dict[str, Any]:
    """Detect objects in image using GPT-4o Vision API"""
    prompt = (
        "List key objects/components visible in this image as JSON. "
        "Preferred shape: {\"objects\": [...], \"notes\": \"...\"}."
    )
    text_output = await _call_gpt4o(prompt, image_data)
    
    try:
        data = json.loads(text_output)
    except json.JSONDecodeError:
        return {"raw_text": text_output}

    if isinstance(data, dict):
        return data
    return {"items": data}

async def extract_text(image_data: bytes) -> str:
    """Extract text from image using GPT-4o Vision API (OCR)"""
    prompt = "Extract all text visible in this image. Return only the text."
    text_output = await _call_gpt4o(prompt, image_data)
    return text_output

async def explain_image(image_data: bytes, question: str | None = None) -> str:
    """Generate image explanation using GPT-4o Vision API"""
    if question:
        prompt = f"Answer the following question about this image: {question}"
    else:
        prompt = "Describe this image in detail, including visible objects, components, and context."
    
    explanation = await _call_gpt4o(prompt, image_data)
    return explanation
