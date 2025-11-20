import asyncio
import json
import os
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
        detected_components_json = Json(objects) if isinstance(objects, dict) else Json({"raw_text": str(objects)})
        ocr_results_json = Json({"text": text})
        scene_description_json = Json({"description": explanation})

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
