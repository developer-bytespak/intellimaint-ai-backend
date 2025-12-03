# iFixit Data Extraction Verification Guide

This document confirms what data is being extracted and stored, and how to verify it's correct.

## ✅ What IS Being Extracted and Stored

### 1. **Text Content (Full Manual Text)** ✅

**YES, the script extracts ALL text content from manuals!**

The script extracts:
- **Guide title**
- **Introduction text**
- **All step titles** (e.g., "Step 1: Remove the battery")
- **All step instructions** (every line of text from each step)
- **Notes, warnings, cautions, and tips** (formatted as markdown)
- **Bullet points** (with proper indentation)
- **Conclusion text**

**Where it's stored:**
- **Field**: `knowledge_sources.raw_content` (TEXT field)
- **Format**: Markdown text
- **Example**: See verification queries below

**How it works:**
The `_render_guide_content()` function processes:
- `guide_detail.steps[]` - All steps from the guide
- `step.lines[]` - All text lines from each step
- `line.text_raw` or `line.text_rendered` or `line.text` - The actual text content

### 2. **Images** ⚠️

**Images are NOT downloaded** - Only image URLs are stored in metadata.

**What's stored:**
- Image URLs (thumbnail, medium, large, original) in `metadata.ifixit.step_images[]`
- **NOT stored**: Actual image binary data

**Why:**
- Images are large (would bloat database)
- URLs allow fetching images on-demand
- Text content is the priority for RAG/search

### 3. **Database Schema Fields** ✅

All required fields are being filled correctly:

#### `equipment_families` (Categories)
| Field | Status | Source |
|-------|--------|--------|
| `id` | ✅ | UUIDv5 from `ifixit/family/{category_path}` |
| `name` | ✅ | Category title |
| `description` | ✅ | Category summary (if available) |
| `metadata` | ✅ | JSON with category info |

#### `equipment_models` (Devices)
| Field | Status | Source |
|-------|--------|--------|
| `id` | ✅ | UUIDv5 from `ifixit/model/{device_path}` |
| `family_id` | ✅ | Foreign key to `equipment_families` |
| `manufacturer` | ✅ | Parsed from device title |
| `model_name` | ✅ | Device title |
| `model_number` | ✅ | Parsed from title (if pattern matches) |
| `description` | ✅ | Device summary (if available) |
| `image_urls` | ⚠️ | NULL (images not downloaded) |
| `metadata` | ✅ | JSON with device info |

#### `knowledge_sources` (Guides/Manuals)
| Field | Status | Source |
|-------|--------|--------|
| `id` | ✅ | UUIDv5 from `ifixit/guide/{guide_id}` |
| `title` | ✅ | Guide title |
| `source_type` | ✅ | Always `"ifixit"` |
| `raw_content` | ✅ | **Full markdown text content** |
| `model_id` | ✅ | Foreign key to `equipment_models` |
| `word_count` | ✅ | Computed from `raw_content` |
| `metadata` | ✅ | JSON with comprehensive guide data |
| `created_at` | ✅ | Auto-generated |
| `updated_at` | ✅ | Auto-updated |

## 🔍 How to Verify Text Content is Extracted

### SQL Query to Check Text Content

```sql
-- Check if guides have text content
SELECT 
  ks.id,
  ks.title,
  LENGTH(ks.raw_content) as content_length,
  ks.word_count,
  LEFT(ks.raw_content, 200) as content_preview,
  ks.metadata->'ifixit'->>'url' as guide_url
FROM knowledge_sources ks
WHERE ks.source_type = 'ifixit'
ORDER BY ks.created_at DESC
LIMIT 10;
```

**Expected Results:**
- `content_length` should be > 0 (usually hundreds or thousands of characters)
- `content_preview` should show markdown text like:
  ```
  # iPhone 4 Battery Replacement
  
  This guide will show you how to replace the battery...
  
  ## 1. Remove the back cover
  
  Use a spudger to pry open...
  ```

### Query to See Full Text Content

```sql
-- Get full text content for a specific guide
SELECT 
  ks.title,
  ks.raw_content,  -- This contains ALL the text!
  ks.word_count,
  em.model_name,
  ks.metadata->'ifixit'->>'url' as guide_url
FROM knowledge_sources ks
JOIN equipment_models em ON em.id = ks.model_id
WHERE ks.source_type = 'ifixit'
  AND ks.title LIKE '%Battery%'  -- Example filter
LIMIT 1;
```

### Query to Verify Content Structure

```sql
-- Check content includes steps, notes, etc.
SELECT 
  ks.title,
  CASE 
    WHEN ks.raw_content LIKE '%##%' THEN 'Has steps'
    ELSE 'No steps found'
  END as has_steps,
  CASE 
    WHEN ks.raw_content LIKE '%Note:%' OR ks.raw_content LIKE '%Warning:%' THEN 'Has notes/warnings'
    ELSE 'No notes/warnings'
  END as has_notes,
  ks.word_count,
  LENGTH(ks.raw_content) as char_count
FROM knowledge_sources ks
WHERE ks.source_type = 'ifixit'
ORDER BY ks.word_count DESC
LIMIT 20;
```

## 🔍 How to Verify Metadata is Stored

### Check Guide Metadata

```sql
-- View metadata structure for a guide
SELECT 
  ks.title,
  ks.metadata->'ifixit'->>'guide_id' as guide_id,
  ks.metadata->'ifixit'->>'url' as guide_url,
  ks.metadata->'ifixit'->>'difficulty' as difficulty,
  ks.metadata->'ifixit'->>'time_required' as time_required,
  jsonb_array_length(COALESCE(ks.metadata->'ifixit'->'step_images', '[]'::jsonb)) as image_count,
  jsonb_array_length(COALESCE(ks.metadata->'ifixit'->'tools', '[]'::jsonb)) as tool_count,
  jsonb_array_length(COALESCE(ks.metadata->'ifixit'->'parts', '[]'::jsonb)) as part_count
FROM knowledge_sources ks
WHERE ks.source_type = 'ifixit'
LIMIT 10;
```

### Check Image URLs in Metadata

```sql
-- View image URLs stored in metadata
SELECT 
  ks.title,
  jsonb_pretty(ks.metadata->'ifixit'->'step_images') as step_images
FROM knowledge_sources ks
WHERE ks.source_type = 'ifixit'
  AND ks.metadata->'ifixit'->'step_images' IS NOT NULL
LIMIT 5;
```

**Expected Output:**
```json
[
  {
    "step_id": 1,
    "image_id": 233436,
    "guid": "H5wkkFSj1tYhJdrg",
    "urls": {
      "thumbnail": "https://www.ifixit.com/...",
      "medium": "https://www.ifixit.com/...",
      "large": "https://www.ifixit.com/...",
      "original": "https://www.ifixit.com/..."
    }
  }
]
```

## 🧪 Test Script to Verify Extraction

Create a test script to verify extraction:

```python
# scripts/ifixit/verify_extraction.py
import sys
from pathlib import Path
from scripts.db_client import DatabaseClient

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def verify_extraction():
    db = DatabaseClient()
    
    # Check if any guides were extracted
    with db.connection.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) as count
            FROM knowledge_sources
            WHERE source_type = 'ifixit'
        """)
        count = cur.fetchone()[0]
        print(f"Total guides extracted: {count}")
        
        if count == 0:
            print("⚠️  No guides found! Run the collector first.")
            return
        
        # Check content length
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN LENGTH(raw_content) > 100 THEN 1 END) as has_content,
                AVG(LENGTH(raw_content)) as avg_length,
                AVG(word_count) as avg_words
            FROM knowledge_sources
            WHERE source_type = 'ifixit'
        """)
        stats = cur.fetchone()
        print(f"\nContent Statistics:")
        print(f"  Total guides: {stats[0]}")
        print(f"  Guides with content (>100 chars): {stats[1]}")
        print(f"  Average content length: {int(stats[2] or 0)} characters")
        print(f"  Average word count: {int(stats[3] or 0)} words")
        
        # Show sample content
        cur.execute("""
            SELECT title, LEFT(raw_content, 300) as preview, word_count
            FROM knowledge_sources
            WHERE source_type = 'ifixit'
              AND LENGTH(raw_content) > 100
            ORDER BY word_count DESC
            LIMIT 3
        """)
        print(f"\nSample Content (top 3 by word count):")
        for row in cur.fetchall():
            print(f"\n  Title: {row[0]}")
            print(f"  Word Count: {row[2]}")
            print(f"  Preview: {row[1][:200]}...")

if __name__ == "__main__":
    verify_extraction()
```

Run it:
```bash
python -m scripts.ifixit.verify_extraction
```

## ❓ Common Questions

### Q: "I see URLs in metadata but not the text content"

**A:** The text content is in the `raw_content` field, NOT in metadata. Metadata contains URLs and structured data. Use the SQL queries above to check `raw_content`.

### Q: "Are images being downloaded?"

**A:** No. Only image URLs are stored in `metadata.ifixit.step_images[]`. The actual image files are NOT downloaded or stored.

### Q: "How do I see the actual text from a guide?"

**A:** Query the `raw_content` field:
```sql
SELECT raw_content FROM knowledge_sources WHERE id = 'your-guide-id';
```

### Q: "The content seems short or empty"

**A:** Some guides may have minimal content. Check:
1. Is `word_count > 0`?
2. Is `LENGTH(raw_content) > 10`?
3. View the guide on iFixit website to verify

### Q: "How do I verify all fields are filled?"

**A:** Run this query:
```sql
SELECT 
  COUNT(*) as total,
  COUNT(CASE WHEN title IS NOT NULL THEN 1 END) as has_title,
  COUNT(CASE WHEN raw_content IS NOT NULL AND LENGTH(raw_content) > 10 THEN 1 END) as has_content,
  COUNT(CASE WHEN model_id IS NOT NULL THEN 1 END) as has_model,
  COUNT(CASE WHEN metadata IS NOT NULL THEN 1 END) as has_metadata,
  COUNT(CASE WHEN word_count IS NOT NULL THEN 1 END) as has_word_count
FROM knowledge_sources
WHERE source_type = 'ifixit';
```

All counts should match `total` (or be very close).

## 📊 Expected Data Quality

After extraction, you should see:

- **Content Length**: Most guides should have 500-5000 characters
- **Word Count**: Most guides should have 100-2000 words
- **Structure**: Content should include:
  - `# Title` (markdown heading)
  - `## Step N` (step headings)
  - Text paragraphs
  - `> **Note:**` or `> ⚠️ **Warning:**` (formatted notes)

## 🚨 Troubleshooting

### Issue: `raw_content` is NULL or empty

**Possible causes:**
1. Guide has no content in iFixit API
2. Content validation failed (too short)
3. API response structure changed

**Solution:**
- Check the guide on iFixit website
- Run with `--log-level DEBUG` to see detailed logs
- Check `failed_devices.json` for errors

### Issue: Content seems incomplete

**Check:**
1. Does the guide have steps? (Check `metadata.ifixit.summary_data`)
2. Are steps being processed? (Check logs for "Processing guide...")
3. Is `guide_detail` being fetched? (Check API response)

## ✅ Summary

**What's Extracted:**
- ✅ **Full text content** (stored in `raw_content`)
- ✅ **All metadata** (stored in `metadata` JSON)
- ✅ **Image URLs** (stored in `metadata.ifixit.step_images`)
- ❌ **Image binaries** (NOT downloaded)

**How to Verify:**
1. Run SQL queries above to check `raw_content` field
2. Check `word_count` is > 0
3. View content preview to see markdown text
4. Run verification script

**If you're not seeing text content:**
- Make sure you're querying the `raw_content` field (not just metadata)
- Verify guides were actually processed (check logs)
- Run a test extraction with `--max-guides-per-device 1` to verify








