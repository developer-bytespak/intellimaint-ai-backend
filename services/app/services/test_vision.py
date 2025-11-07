import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

ROOT_DIR = CURRENT_DIR
for _ in range(3):
    if ROOT_DIR.parent == ROOT_DIR:
        break
    ROOT_DIR = ROOT_DIR.parent

dotenv_path = ROOT_DIR / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)
else:
    load_dotenv()

try:
    from vision_service import detect_objects, explain_image, extract_text
except RuntimeError as exc:
    if "OPENAI_API_KEY" in str(exc):
        raise RuntimeError(
            "OPENAI_API_KEY must be set before running test_vision.py. "
            "Example PowerShell: `setx OPENAI_API_KEY \"sk-...\"` and restart shell."
        ) from exc
    raise

IMAGE_PATH = CURRENT_DIR.parent / "storage" / "images" / "washing_machine.jpeg"


async def main() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for testing.")
    if not IMAGE_PATH.exists():
        raise FileNotFoundError(f"Test image not found at {IMAGE_PATH}")

    image_bytes = IMAGE_PATH.read_bytes()

    objects = await detect_objects(image_bytes)
    print("Detected objects:", objects)

    text = await extract_text(image_bytes)
    print("Extracted text:", text)

    explanation = await explain_image(image_bytes)
    print("Image explanation:", explanation)


if __name__ == "__main__":
    asyncio.run(main())
