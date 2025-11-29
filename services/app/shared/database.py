# db.py
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

def create_db_client() -> Client:
    """Create and return a Supabase client with validation."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not url or not key:
        raise ValueError("Supabase URL or KEY missing in .env")

    return create_client(url, key)

def check_db_connection() -> dict:
    """Check Supabase connection without touching any user tables."""
    try:
        db = create_db_client()

        # Call a built-in function to test connection (NO table required)
        health = db.postgrest.from_('pg_tables').select("tablename").limit(1).execute()

        return {
            "status": "ok",
            "message": "Supabase connection successful",
            "details": health.data
        }

    except Exception as e:
        return {
            "status": "error",
            "message": "Supabase connection failed",
            "error": str(e)
        }

def get_db() -> Client:
    """Get the Supabase client (used throughout the app)."""
    return create_db_client()
