"""Show full content of guides to verify no truncation."""
import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
env_paths = [
    project_root / '.env',
    project_root / 'gateway' / '.env',
]
for env_path in env_paths:
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
        break
else:
    load_dotenv(override=False)

from scripts.db_client import DatabaseClient

def show_full_content(title_filter=None, limit=None, show_images_in_text=False):
    """Show full content of guides."""
    try:
        db = DatabaseClient()
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return 1

    with db.transaction() as cur:
        # Build query
        query = """
            SELECT title, raw_content, LENGTH(raw_content) as len, metadata
            FROM knowledge_sources
            WHERE source_type = 'ifixit'
        """
        params = []
        
        if title_filter:
            query += " AND title LIKE %s"
            params.append(f"%{title_filter}%")
        
        query += " ORDER BY LENGTH(raw_content) DESC"
        
        if limit:
            query += " LIMIT %s"
            params.append(limit)
        
        cur.execute(query, params)
        rows = cur.fetchall()
        
        if not rows:
            print("❌ No guides found")
            return 1
        
        print(f"📚 Found {len(rows)} guide(s)\n")
        
        for idx, (title, content, length, metadata_json) in enumerate(rows, 1):
            print(f"{'='*80}")
            print(f"Guide {idx}: {title}")
            print(f"{'='*80}")
            print(f"Length: {length:,} characters")
            
            # Check if images are in text
            if show_images_in_text:
                has_images = "![Image" in content or "Image URLs:" in content or "<!-- Image URLs:" in content
                print(f"Images in text: {'✅ Yes' if has_images else '❌ No (extracted before image inclusion fix)'}")
            
            print(f"\n{'='*80}")
            print("FULL CONTENT (no truncation):")
            print(f"{'='*80}\n")
            print(content)
            print(f"\n{'='*80}")
            print(f"End of content ({length:,} characters total)")
            
            if idx < len(rows):
                print(f"\n\n")
        
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Show full content of iFixit guides")
    parser.add_argument("--title", help="Filter by title (partial match)")
    parser.add_argument("--limit", type=int, help="Limit number of guides to show")
    parser.add_argument("--check-images", action="store_true", help="Check if images are included in text")
    args = parser.parse_args()
    
    sys.exit(show_full_content(
        title_filter=args.title,
        limit=args.limit,
        show_images_in_text=args.check_images
    ))

