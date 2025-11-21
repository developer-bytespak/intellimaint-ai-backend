#!/usr/bin/env python3
"""Verify that iFixit data extraction is working correctly."""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables from .env file
# Try multiple locations (project root and gateway directory)
env_paths = [
    project_root / '.env',
    project_root / 'gateway' / '.env',
]
for env_path in env_paths:
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
        break
else:
    # If no .env file found, try loading from current directory
    load_dotenv(override=False)

from scripts.db_client import DatabaseClient


def verify_extraction():
    """Verify that guides have been extracted with text content."""
    try:
        db = DatabaseClient()
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("\n💡 Troubleshooting:")
        print("   1. Check if DATABASE_URL is set in your environment:")
        print("      - Windows: echo %DATABASE_URL%")
        print("      - Or check if it's in a .env file")
        print("   2. Create .env file in project root with:")
        print("      DATABASE_URL=postgresql://user:password@host:port/database")
        print("   3. Or set it as environment variable before running:")
        print("      $env:DATABASE_URL='postgresql://...'  # PowerShell")
        print("      export DATABASE_URL='postgresql://...'  # Bash")
        
        # Check if DATABASE_URL exists in environment
        db_url = os.getenv("DATABASE_URL")
        if db_url:
            print(f"\n   ⚠️  DATABASE_URL is set but connection failed.")
            print(f"   Check if the connection string is correct.")
        else:
            print(f"\n   ⚠️  DATABASE_URL is not set in environment.")
        
        return 1

    print("🔍 Verifying iFixit data extraction...\n")

    with db.transaction() as cur:
        # Check if any guides were extracted
        cur.execute("""
            SELECT COUNT(*) as count
            FROM knowledge_sources
            WHERE source_type = 'ifixit'
        """)
        count = cur.fetchone()[0]
        print(f"📊 Total guides extracted: {count}")

        if count == 0:
            print("\n⚠️  No guides found! Run the collector first:")
            print("   python -m scripts.ifixit.collect_ifixit_data --max-devices-per-category 1 --max-guides-per-device 3")
            return 1

        # Check content statistics
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN LENGTH(raw_content) > 100 THEN 1 END) as has_content,
                COUNT(CASE WHEN LENGTH(raw_content) > 1000 THEN 1 END) as has_long_content,
                AVG(LENGTH(raw_content)) as avg_length,
                AVG(word_count) as avg_words,
                MIN(LENGTH(raw_content)) as min_length,
                MAX(LENGTH(raw_content)) as max_length
            FROM knowledge_sources
            WHERE source_type = 'ifixit'
        """)
        stats = cur.fetchone()
        total, has_content, has_long_content, avg_len, avg_words, min_len, max_len = stats

        print(f"\n📝 Content Statistics:")
        print(f"   Total guides: {total}")
        print(f"   Guides with content (>100 chars): {has_content} ({has_content*100//total if total > 0 else 0}%)")
        print(f"   Guides with long content (>1000 chars): {has_long_content} ({has_long_content*100//total if total > 0 else 0}%)")
        print(f"   Average content length: {int(avg_len or 0)} characters")
        print(f"   Average word count: {int(avg_words or 0)} words")
        print(f"   Min length: {min_len or 0} chars")
        print(f"   Max length: {max_len or 0} chars")

        # Check field completeness
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN title IS NOT NULL AND title != '' THEN 1 END) as has_title,
                COUNT(CASE WHEN raw_content IS NOT NULL AND LENGTH(raw_content) > 10 THEN 1 END) as has_content,
                COUNT(CASE WHEN model_id IS NOT NULL THEN 1 END) as has_model,
                COUNT(CASE WHEN metadata IS NOT NULL THEN 1 END) as has_metadata,
                COUNT(CASE WHEN word_count IS NOT NULL AND word_count > 0 THEN 1 END) as has_word_count
            FROM knowledge_sources
            WHERE source_type = 'ifixit'
        """)
        completeness = cur.fetchone()
        total_check, has_title, has_content_check, has_model, has_metadata, has_word_count = completeness

        print(f"\n✅ Field Completeness:")
        print(f"   Has title: {has_title}/{total_check} ({has_title*100//total_check if total_check > 0 else 0}%)")
        print(f"   Has content: {has_content_check}/{total_check} ({has_content_check*100//total_check if total_check > 0 else 0}%)")
        print(f"   Has model_id: {has_model}/{total_check} ({has_model*100//total_check if total_check > 0 else 0}%)")
        print(f"   Has metadata: {has_metadata}/{total_check} ({has_metadata*100//total_check if total_check > 0 else 0}%)")
        print(f"   Has word_count: {has_word_count}/{total_check} ({has_word_count*100//total_check if total_check > 0 else 0}%)")

        # Show sample content
        cur.execute("""
            SELECT 
                ks.title, 
                LEFT(ks.raw_content, 400) as preview, 
                ks.word_count,
                LENGTH(ks.raw_content) as content_length,
                em.model_name,
                ks.metadata->'ifixit'->>'url' as guide_url
            FROM knowledge_sources ks
            LEFT JOIN equipment_models em ON em.id = ks.model_id
            WHERE ks.source_type = 'ifixit'
              AND LENGTH(ks.raw_content) > 100
            ORDER BY ks.word_count DESC
            LIMIT 3
        """)
        samples = cur.fetchall()

        print(f"\n📄 Sample Content (top 3 by word count):")
        for idx, (title, preview, word_count, content_length, model_name, guide_url) in enumerate(samples, 1):
            print(f"\n   {idx}. {title}")
            print(f"      Model: {model_name or 'N/A'}")
            print(f"      Word Count: {word_count}")
            print(f"      Content Length: {content_length} characters")
            if guide_url:
                print(f"      URL: {guide_url}")
            print(f"      Preview:")
            # Show first 300 chars of preview
            preview_text = preview[:300].replace('\n', ' ').strip()
            print(f"      {preview_text}...")

        # Check content structure
        cur.execute("""
            SELECT 
                COUNT(CASE WHEN raw_content LIKE '%##%' THEN 1 END) as has_steps,
                COUNT(CASE WHEN raw_content LIKE '%Note:%' OR raw_content LIKE '%Warning:%' OR raw_content LIKE '%Caution:%' THEN 1 END) as has_notes,
                COUNT(CASE WHEN raw_content LIKE '%# %' THEN 1 END) as has_title_markdown
            FROM knowledge_sources
            WHERE source_type = 'ifixit'
              AND LENGTH(raw_content) > 100
        """)
        structure = cur.fetchone()
        has_steps, has_notes, has_title_md = structure

        print(f"\n📋 Content Structure Analysis:")
        print(f"   Guides with step headings (##): {has_steps}")
        print(f"   Guides with notes/warnings: {has_notes}")
        print(f"   Guides with markdown title (#): {has_title_md}")

        # Check metadata
        cur.execute("""
            SELECT 
                COUNT(CASE WHEN metadata->'ifixit'->>'guide_id' IS NOT NULL THEN 1 END) as has_guide_id,
                COUNT(CASE WHEN metadata->'ifixit'->>'url' IS NOT NULL THEN 1 END) as has_url,
                COUNT(CASE WHEN metadata->'ifixit'->'step_images' IS NOT NULL THEN 1 END) as has_images,
                COUNT(CASE WHEN metadata->'ifixit'->'tools' IS NOT NULL THEN 1 END) as has_tools,
                COUNT(CASE WHEN metadata->'ifixit'->'parts' IS NOT NULL THEN 1 END) as has_parts
            FROM knowledge_sources
            WHERE source_type = 'ifixit'
        """)
        metadata_stats = cur.fetchone()
        has_guide_id, has_url, has_images, has_tools, has_parts = metadata_stats

        print(f"\n🔗 Metadata Completeness:")
        print(f"   Has guide_id: {has_guide_id}/{total_check}")
        print(f"   Has URL: {has_url}/{total_check}")
        print(f"   Has step_images: {has_images}/{total_check}")
        print(f"   Has tools: {has_tools}/{total_check}")
        print(f"   Has parts: {has_parts}/{total_check}")

        # Summary
        print(f"\n{'='*60}")
        if has_content_check == total_check and has_title == total_check:
            print("✅ VERIFICATION PASSED: All guides have text content!")
        elif has_content_check > total_check * 0.9:
            print("⚠️  VERIFICATION WARNING: Some guides may be missing content")
        else:
            print("❌ VERIFICATION FAILED: Many guides are missing content")
            print("   Check the extraction logs for errors")

        print(f"\n💡 To view full content of a guide, run:")
        print(f"   SELECT raw_content FROM knowledge_sources WHERE source_type = 'ifixit' LIMIT 1;")

    return 0


if __name__ == "__main__":
    sys.exit(verify_extraction())

