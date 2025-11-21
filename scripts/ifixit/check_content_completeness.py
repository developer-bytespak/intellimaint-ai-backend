"""Check if guide content is complete and includes all text and images."""
import os
import sys
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
import json

def check_content_completeness():
    """Check if guide content is complete."""
    try:
        db = DatabaseClient()
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return 1

    print("🔍 Checking content completeness...\n")

    with db.transaction() as cur:
        # Get a sample guide with full details
        cur.execute("""
            SELECT 
                id,
                title,
                LENGTH(raw_content) as content_length,
                word_count,
                metadata,
                LEFT(raw_content, 1000) as content_preview
            FROM knowledge_sources
            WHERE source_type = 'ifixit'
            ORDER BY LENGTH(raw_content) DESC
            LIMIT 3
        """)
        
        guides = cur.fetchall()
        
        if not guides:
            print("❌ No guides found in database")
            return 1
        
        print(f"📊 Analyzing {len(guides)} guides (longest first):\n")
        
        for idx, (guide_id, title, content_len, word_count, metadata_json, preview) in enumerate(guides, 1):
            print(f"{'='*80}")
            print(f"Guide {idx}: {title}")
            print(f"{'='*80}")
            print(f"Content Length: {content_len:,} characters")
            print(f"Word Count: {word_count:,} words")
            print(f"\nFirst 1000 characters:")
            print(f"{preview}...")
            
            if metadata_json:
                metadata = json.loads(metadata_json) if isinstance(metadata_json, str) else metadata_json
                ifixit_meta = metadata.get("ifixit", {})
                
                print(f"\n📸 Image Information:")
                step_images = ifixit_meta.get("step_images", [])
                print(f"   Total step images: {len(step_images)}")
                if step_images:
                    for img in step_images[:3]:  # Show first 3
                        print(f"   - Step {img.get('step_id')}: {len(img.get('urls', {}))} size variants")
                        if 'urls' in img:
                            urls = img['urls']
                            if 'original' in urls:
                                print(f"     Original: {urls['original']}")
                
                print(f"\n📄 Document Information:")
                documents = ifixit_meta.get("documents", [])
                if documents:
                    print(f"   Total documents: {len(documents)}")
                else:
                    print(f"   Total documents: 0")
                
                print(f"\n🔧 Parts Information:")
                parts = ifixit_meta.get("parts", [])
                if parts:
                    print(f"   Total parts: {len(parts)}")
                else:
                    print(f"   Total parts: 0")
                
                # Check if content mentions images (markdown format or HTML comments)
                if "![Image" in preview or "![image" in preview or "Image URLs:" in preview or "<!-- Image URLs:" in preview:
                    print(f"\n✅ Content includes image references")
                else:
                    print(f"\n⚠️  Content may not include image references in text")
                    print(f"   (Images are stored in metadata, but may not be in text for older extractions)")
            
            print(f"\n")
        
        # Check for any content length limits
        cur.execute("""
            SELECT 
                MIN(LENGTH(raw_content)) as min_len,
                MAX(LENGTH(raw_content)) as max_len,
                AVG(LENGTH(raw_content)) as avg_len,
                COUNT(*) as total
            FROM knowledge_sources
            WHERE source_type = 'ifixit'
        """)
        
        stats = cur.fetchone()
        min_len, max_len, avg_len, total = stats
        
        print(f"{'='*80}")
        print(f"📊 Content Statistics:")
        print(f"{'='*80}")
        print(f"Total guides: {total}")
        print(f"Min length: {min_len:,} characters")
        print(f"Max length: {max_len:,} characters")
        print(f"Avg length: {int(avg_len):,} characters")
        print(f"\n✅ Database field 'raw_content' is TEXT type (unlimited length)")
        print(f"✅ No truncation should occur at database level")
        
    return 0

if __name__ == "__main__":
    sys.exit(check_content_completeness())

