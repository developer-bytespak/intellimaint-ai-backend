import asyncio
import json
import os
import re
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

import psycopg2
import tiktoken
from dotenv import load_dotenv
from psycopg2.extras import Json

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

# Database connection helper
def get_db_connection():
    """Get database connection using DATABASE_URL from environment."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return psycopg2.connect(database_url)


@contextmanager
def db_transaction():
    """Context manager for database transactions."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
    finally:
        conn.close()


def create_dummy_attachment(image_path: Path) -> str:
    """
    Create dummy User → ChatSession (reused) → ChatMessage → MessageAttachment chain.
    Returns the attachment ID.
    """
    with db_transaction() as cur:
        # Check if dummy user exists, create if not
        dummy_user_email = "test-vision@intellimaint.local"
        cur.execute("SELECT id FROM users WHERE email = %s", (dummy_user_email,))
        user_row = cur.fetchone()
        
        if user_row:
            user_id = user_row[0]
        else:
            user_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO users (id, email, email_verified, role, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                """,
                (user_id, dummy_user_email, False, "civilian", "ACTIVE"),
            )
        
        # Check if chat session exists for this user, create if not
        cur.execute(
            "SELECT id FROM chat_sessions WHERE user_id = %s AND status = 'active' ORDER BY created_at ASC LIMIT 1",
            (user_id,)
        )
        session_row = cur.fetchone()
        
        if session_row:
            session_id = session_row[0]
        else:
            session_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO chat_sessions (id, user_id, status, created_at, updated_at)
                VALUES (%s, %s, %s, NOW(), NOW())
                """,
                (session_id, user_id, "active"),
            )
        
        # Create new ChatMessage in the session
        message_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO chat_messages (id, session_id, role, created_at)
            VALUES (%s, %s, %s, NOW())
            """,
            (message_id, session_id, "user"),
        )
        
        # Create new MessageAttachment for the message
        attachment_id = str(uuid.uuid4())
        file_url = f"file://{image_path.absolute()}"
        file_name = image_path.name
        cur.execute(
            """
            INSERT INTO message_attachments (id, message_id, attachment_type, file_url, file_name, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (attachment_id, message_id, "image", file_url, file_name),
        )
        
        return attachment_id


def parse_detected_components(objects: dict) -> dict:
    """
    Parse detected components, extracting JSON from markdown if needed.
    Returns structured data: {"objects": [...], "notes": "..."}
    """
    # If it's already properly structured, return it
    if "objects" in objects and isinstance(objects.get("objects"), list):
        return objects
    
    # If we have raw_text, try to extract JSON from markdown code blocks
    if "raw_text" in objects:
        raw_text = objects["raw_text"]
        
        # Try to extract JSON from markdown code blocks (```json ... ```)
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1))
                if isinstance(parsed, dict) and "objects" in parsed:
                    return parsed
            except json.JSONDecodeError:
                pass
        
        # Try direct JSON parsing (in case it's just JSON without markdown)
        try:
            parsed = json.loads(raw_text)
            if isinstance(parsed, dict) and "objects" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass
        
        # If all parsing fails, return structured format with raw text
        return {
            "raw_text": raw_text,
            "parsed": False,
            "objects": [],
            "notes": "Failed to parse detected components"
        }
    
    # If it's some other format, try to normalize it
    if "items" in objects:
        return {"objects": objects["items"], "notes": objects.get("notes", "")}
    
    # Fallback: return as-is but ensure structure
    return {
        "objects": [],
        "notes": "",
        "raw_data": objects
    }


def clean_ocr_text(text: str) -> dict:
    """
    Clean and structure OCR text.
    Returns structured data with text and lines array.
    """
    if not text:
        return {
            "text": "",
            "lines": []
        }
    
    # Split by newlines, strip each line, and filter empty lines
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    # Rejoin with single newlines for cleaned text
    cleaned_text = '\n'.join(lines)
    
    return {
        "text": cleaned_text,
        "lines": lines
    }


def parse_scene_description(description: str) -> dict:
    """
    Parse and structure scene description.
    Extracts main description, components, and context from markdown-formatted description.
    """
    if not description:
        return {
            "description": "",
            "components": {},
            "context": {}
        }
    
    # Initialize result structure
    result = {
        "description": description,
        "components": {},
        "context": {}
    }
    
    # Extract main description (text before first ###)
    main_match = re.match(r'^(.*?)(?=\n###|$)', description, re.DOTALL)
    if main_match:
        result["summary"] = main_match.group(1).strip()
    
    # Extract Components section
    components_match = re.search(r'###\s*Components:\s*\n(.*?)(?=###|$)', description, re.DOTALL)
    if components_match:
        components_text = components_match.group(1)
        # Extract bullet points with **key:** value format
        bullets = re.findall(r'[-*]\s*\*\*([^:]+):\*\*\s*\n?\s*(.*?)(?=\n[-*]|$)', components_text, re.DOTALL)
        for key, value in bullets:
            key_clean = key.strip().lower().replace(' ', '_')
            result["components"][key_clean] = value.strip()
    
    # Extract Context section
    context_match = re.search(r'###\s*Context:\s*\n(.*?)(?=###|Overall|$)', description, re.DOTALL)
    if context_match:
        context_text = context_match.group(1)
        # Extract bullet points with **key:** value format
        bullets = re.findall(r'[-*]\s*\*\*([^:]+):\*\*\s*\n?\s*(.*?)(?=\n[-*]|$)', context_text, re.DOTALL)
        for key, value in bullets:
            key_clean = key.strip().lower().replace(' ', '_')
            result["context"][key_clean] = value.strip()
    
    # Extract Overall summary if present
    overall_match = re.search(r'Overall[^,]*,\s*(.*?)$', description, re.DOTALL)
    if overall_match:
        result["overall"] = overall_match.group(1).strip()
    
    return result


def calculate_token_count(*texts: str) -> int:
    """
    Calculate total token count for given texts using tiktoken.
    Uses cl100k_base encoding (for GPT-4o-mini).
    """
    encoding = tiktoken.get_encoding("cl100k_base")
    total_tokens = 0
    for text in texts:
        if text:
            tokens = encoding.encode(str(text))
            total_tokens += len(tokens)
    return total_tokens


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

    # Calculate token count from all responses
    objects_text = json.dumps(objects) if isinstance(objects, dict) else str(objects)
    token_count = calculate_token_count(objects_text, text, explanation)
    print(f"\nTotal token count: {token_count}")

    # Create dummy MessageAttachment and store results in database
    try:
        attachment_id = create_dummy_attachment(IMAGE_PATH)
        print(f"Created dummy attachment with ID: {attachment_id}")

        # Prepare data for database insertion
        detected_components = parse_detected_components(objects)
        detected_components_json = Json(detected_components)
        ocr_results = clean_ocr_text(text)
        ocr_results_json = Json(ocr_results)
        scene_description = parse_scene_description(explanation)
        scene_description_json = Json(scene_description)

        # Insert ImageAnalysis record
        with db_transaction() as cur:
            analysis_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO image_analysis (
                    id, attachment_id, detected_components, ocr_results, 
                    scene_description, token_count, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                """,
                (
                    analysis_id,
                    attachment_id,
                    detected_components_json,
                    ocr_results_json,
                    scene_description_json,
                    token_count,
                ),
            )
            print(f"\n✓ Successfully stored image analysis in database!")
            print(f"  Analysis ID: {analysis_id}")
            print(f"  Attachment ID: {attachment_id}")
            print(f"  Token count: {token_count}")
    except Exception as e:
        print(f"\n✗ Error storing results in database: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
