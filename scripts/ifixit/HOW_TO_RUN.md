# How to Run iFixit Data Collection and Store in Database

This guide provides step-by-step instructions for running the iFixit collection script to extract manuals and store them in your PostgreSQL database.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Database Setup](#database-setup)
3. [Configuration](#configuration)
4. [Running the Script](#running-the-script)
5. [What Gets Stored Where](#what-gets-stored-where)
6. [Verification](#verification)
7. [Troubleshooting](#troubleshooting)

## Prerequisites

### 1. Python Environment

- **Python 3.8+** (Python 3.13 tested and working)
- Install dependencies from project root:

```bash
cd C:\Users\AS\Desktop\intellimaint\intellimaint-ai-backend
pip install -r scripts/requirements.txt
```

**Note**: If you encounter issues with `psycopg2-binary` on Python 3.13, install without version pinning:
```bash
pip install psycopg2-binary requests python-dotenv tqdm tenacity
```

### 2. Database Schema

Ensure your database schema is up to date with the required metadata fields:

```bash
cd gateway
npx prisma migrate deploy
npx prisma generate
```

**Required Schema Fields:**
- `equipment_families.metadata` (JSONB) - for category metadata
- `equipment_models.metadata` (JSONB) - for device metadata  
- `knowledge_sources.metadata` (JSONB) - for guide metadata (already exists)

If these fields don't exist, run the migration:
```bash
npx prisma migrate dev --name add_metadata_to_equipment_tables
```

## Database Setup

### 1. Configure Database Connection

Create or update `.env` file in the project root:

```env
# Required: Database connection string
DATABASE_URL=postgresql://user:password@host:port/database

# Example for Neon (PostgreSQL):
# DATABASE_URL=postgresql://user:password@ep-sweet-term-a400zy46-pooler.us-east-1.aws.neon.tech/neondb

# Optional: iFixit API key (for higher rate limits)
IFIXIT_API_KEY=your_api_key_here
```

**Important**: 
- The `DATABASE_URL` must be accessible from your machine
- Format: `postgresql://username:password@hostname:port/database_name`
- For cloud databases (Neon, Supabase, etc.), use the connection string provided by your provider

### 2. Verify Database Connection

Test the database connection:

```bash
python -c "from scripts.db_client import DatabaseClient; db = DatabaseClient(); print('Database connection successful!')"
```

If this fails, check:
- Database server is running
- `DATABASE_URL` is correct
- Network/firewall allows connection
- Credentials are valid

## Configuration

### Environment Variables

The script reads configuration from environment variables (via `.env` file):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | **Yes** | None | PostgreSQL connection string |
| `IFIXIT_API_KEY` | No | "" | Optional API key for higher rate limits |
| `IFIXIT_RATE_LIMIT_RPS` | No | 2 | Requests per second (rate limiting) |
| `IFIXIT_REQUEST_TIMEOUT` | No | 30 | Request timeout in seconds |
| `IFIXIT_MAX_RETRIES` | No | 3 | Maximum retry attempts |

### Rate Limiting

The script respects iFixit API rate limits:
- **Default**: 2 requests per second (0.5s delay between requests)
- **With API Key**: Higher limits may apply
- **Adjustable**: Set `IFIXIT_RATE_LIMIT_RPS` in `.env` to change rate

## Running the Script

### Step 1: Test with Dry Run (Recommended First)

Always test with `--dry-run` first to verify everything works without writing to database:

```bash
# From project root directory
python -m scripts.ifixit.collect_ifixit_data \
  --dry-run \
  --max-devices-per-category 2 \
  --max-guides-per-device 3
```

**What `--dry-run` does:**
- Fetches data from iFixit API
- Processes and validates content
- **Does NOT write to database**
- Shows what would be stored

### Step 2: Test with Small Sample (Write to Database)

Once dry-run works, test with a small sample that actually writes to database:

```bash
# Test with 1 category, 2 devices, 3 guides each
python -m scripts.ifixit.collect_ifixit_data \
  --category Phone \
  --max-devices-per-category 2 \
  --max-guides-per-device 3
```

### Step 3: Run Full Extraction

When ready, run the full extraction:

```bash
# Full extraction (all categories, all devices, all guides)
python -m scripts.ifixit.collect_ifixit_data \
  --log-level INFO \
  --checkpoint-interval 50 \
  --concurrency 4
```

**Command Options:**

| Option | Description | Example |
|--------|-------------|---------|
| `--category NAME` | Process specific category | `--category Phone` |
| `--device PATH` | Process specific device | `--device "Phone/iPhone/iPhone 4"` |
| `--max-devices-per-category N` | Limit devices per category | `--max-devices-per-category 10` |
| `--max-guides-per-device N` | Limit guides per device | `--max-guides-per-device 5` |
| `--concurrency N` | Concurrent workers (default: 4) | `--concurrency 8` |
| `--resume` | Resume from last checkpoint | `--resume` |
| `--retry-failed` | Retry only failed devices | `--retry-failed` |
| `--dry-run` | Test without database writes | `--dry-run` |
| `--log-level LEVEL` | Logging level (DEBUG/INFO/WARNING/ERROR) | `--log-level DEBUG` |

### Step 4: Monitor Progress

The script provides progress information:

```
2025-11-14 04:23:02 [INFO] Processing category 'Mac' with 2 devices
2025-11-14 04:23:03 [INFO] Processing 20 guides for device 'Mac/Mac Hardware/Apple Time Capsule/Apple Time Capsule Model A1302'
2025-11-14 04:23:15 [INFO] Device completed - guides_processed: 20
```

**Progress Files:**
- `scripts/ifixit/state/ingest_state.csv` - Progress ledger
- `scripts/ifixit/checkpoints/checkpoint_*.json` - Checkpoint snapshots
- `scripts/ifixit/state/failed_devices.json` - Failed devices report

### Step 5: Resume if Interrupted

If the script stops (Ctrl+C, network issue, etc.), resume from checkpoint:

```bash
# Resume from last checkpoint
python -m scripts.ifixit.collect_ifixit_data --resume
```

**Note**: The script uses deterministic UUIDs, so re-running is safe (upserts existing records).

### Step 6: Retry Failed Devices

After completion, retry any failed devices:

```bash
# Retry only devices that failed
python -m scripts.ifixit.collect_ifixit_data --retry-failed
```

## What Gets Stored Where

### Database Tables and Fields

#### 1. `equipment_families` (Categories)

| Field | Source | Example |
|-------|--------|---------|
| `id` | UUIDv5 from `ifixit/family/{category_path}` | Deterministic UUID |
| `name` | Category title | "Phone", "Mac", "Camera" |
| `description` | Category summary (if available) | NULL or text |
| `metadata` | JSON with category info | `{"ifixit": {"path": "Phone", "device_count": 5000, "processed_at": "2025-11-14T..."}}` |

**Example Query:**
```sql
SELECT id, name, metadata->'ifixit'->>'path' as category_path
FROM equipment_families
WHERE metadata->'ifixit' IS NOT NULL;
```

#### 2. `equipment_models` (Devices)

| Field | Source | Example |
|-------|--------|---------|
| `id` | UUIDv5 from `ifixit/model/{device_path}` | Deterministic UUID |
| `family_id` | UUID from `equipment_families` | Foreign key |
| `manufacturer` | Parsed from device title | "Apple", "Samsung" |
| `model_name` | Device title | "iPhone 4", "MacBook Pro" |
| `model_number` | Parsed from title (if pattern matches) | "A1302", "MBP13" |
| `description` | Device summary (if available) | NULL or text |
| `image_urls` | NULL (images not downloaded) | NULL |
| `metadata` | JSON with device info | `{"ifixit": {"path": "Phone/iPhone/iPhone 4", "title": "iPhone 4", "raw": {...}, "processed_at": "2025-11-14T..."}}` |

**Example Query:**
```sql
SELECT 
  em.id,
  em.model_name,
  em.manufacturer,
  em.metadata->'ifixit'->>'path' as device_path,
  COUNT(ks.id) as guide_count
FROM equipment_models em
LEFT JOIN knowledge_sources ks ON ks.model_id = em.id AND ks.source_type = 'ifixit'
WHERE em.metadata->'ifixit' IS NOT NULL
GROUP BY em.id, em.model_name, em.manufacturer
ORDER BY guide_count DESC;
```

#### 3. `knowledge_sources` (Guides/Manuals)

| Field | Source | Example |
|-------|--------|---------|
| `id` | UUIDv5 from `ifixit/guide/{guide_id}` | Deterministic UUID |
| `title` | Guide title | "iPhone 4 Battery Replacement" |
| `source_type` | Always `"ifixit"` | "ifixit" |
| `raw_content` | Rendered markdown text | Full guide content as markdown |
| `model_id` | UUID from `equipment_models` | Foreign key |
| `word_count` | Computed from `raw_content` | 1250 |
| `metadata` | JSON with comprehensive guide data | See metadata structure below |
| `created_at` | Timestamp | Auto-generated |
| `updated_at` | Timestamp | Auto-updated on upsert |

**Metadata Structure:**
```json
{
  "ifixit": {
    "guide_id": 12345,
    "url": "https://www.ifixit.com/Guide/iPhone+4+Battery+Replacement/12345",
    "difficulty": "Easy",
    "time_required": "15 minutes",
    "time_required_min": 10,
    "time_required_max": 20,
    "type": "replacement",
    "subject": "Battery",
    "locale": "en",
    "revisionid": 1357831,
    "modified_date": 1736973864,
    "tools": [
      {
        "name": "Spudger",
        "url": "https://www.ifixit.com/Store/Tools/Spudger/IF145-001"
      }
    ],
    "parts": [
      {
        "name": "iPhone 4 Battery",
        "url": "https://www.ifixit.com/Store/Parts/iPhone+4+Battery/IF123-001",
        "full_url": "https://www.ifixit.com/Store/Parts/iPhone+4+Battery/IF123-001"
      }
    ],
    "step_images": [
      {
        "step_id": 1,
        "image_id": 233436,
        "guid": "H5wkkFSj1tYhJdrg",
        "urls": {
          "thumbnail": "https://...",
          "medium": "https://...",
          "large": "https://...",
          "original": "https://..."
        }
      }
    ],
    "author": {
      "userid": 1,
      "username": "iRobot",
      "url": "https://www.ifixit.com/User/1"
    },
    "documents": [
      {
        "id": "doc123",
        "detail_url": "https://www.ifixit.com/api/2.0/documents/doc123",
        "download_url": "https://www.ifixit.com/...",
        "title": "PDF Manual"
      }
    ],
    "featured_document": {
      "document_id": "doc456",
      "embed_url": "https://...",
      "thumbnail_url": "https://...",
      "detail_url": "https://www.ifixit.com/api/2.0/documents/doc456"
    },
    "flags": [],
    "prerequisites": [],
    "summary_data": {...}
  }
}
```

**Example Query:**
```sql
-- Get all guides for a specific device
SELECT 
  ks.id,
  ks.title,
  ks.word_count,
  ks.metadata->'ifixit'->>'url' as guide_url,
  ks.metadata->'ifixit'->>'difficulty' as difficulty,
  ks.metadata->'ifixit'->>'time_required' as time_required
FROM knowledge_sources ks
JOIN equipment_models em ON em.id = ks.model_id
WHERE ks.source_type = 'ifixit'
  AND em.model_name = 'iPhone 4'
ORDER BY ks.created_at DESC;
```

## Verification

### 1. Check Data Was Stored

```sql
-- Count total guides extracted
SELECT COUNT(*) as total_guides 
FROM knowledge_sources 
WHERE source_type = 'ifixit';

-- Count by category
SELECT 
  ef.name as category,
  COUNT(DISTINCT em.id) as devices,
  COUNT(ks.id) as guides
FROM equipment_families ef
LEFT JOIN equipment_models em ON em.family_id = ef.id
LEFT JOIN knowledge_sources ks ON ks.model_id = em.id AND ks.source_type = 'ifixit'
WHERE ef.metadata->'ifixit' IS NOT NULL
GROUP BY ef.name
ORDER BY guides DESC;

-- Check a specific guide
SELECT 
  ks.title,
  ks.raw_content,
  ks.metadata->'ifixit'->>'url' as url,
  em.model_name
FROM knowledge_sources ks
JOIN equipment_models em ON em.id = ks.model_id
WHERE ks.source_type = 'ifixit'
LIMIT 1;
```

### 2. Validate Data Quality

Run the validation script:

```bash
python -m scripts.ifixit.validate_extraction
```

This checks:
- All families have metadata
- All models are linked correctly
- All guides have content
- All relationships are valid

### 3. Check Progress Files

```bash
# View progress ledger
cat scripts/ifixit/state/ingest_state.csv

# View failed devices
cat scripts/ifixit/state/failed_devices.json

# List checkpoints
ls -lt scripts/ifixit/checkpoints/ | head -5
```

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'scripts'"

**Solution**: Run from project root directory:
```bash
cd C:\Users\AS\Desktop\intellimaint\intellimaint-ai-backend
python -m scripts.ifixit.collect_ifixit_data
```

### Issue: "DatabaseConnectionError: DATABASE_URL is not set"

**Solution**: 
1. Create `.env` file in project root
2. Add `DATABASE_URL=postgresql://...`
3. Verify file is in correct location

### Issue: "ERROR: column 'metadata' does not exist"

**Solution**: Run database migration:
```bash
cd gateway
npx prisma migrate deploy
```

### Issue: Script is slow / taking too long

**Explanation**: This is normal! With rate limiting:
- ~0.5s delay between requests
- ~20 guides per device
- ~10 seconds per device minimum
- Full extraction: ~4-5 days

**Solutions**:
- Use `--max-devices-per-category` to limit scope
- Process categories separately
- Increase `--concurrency` (if rate limits allow)
- Use `IFIXIT_API_KEY` for higher limits

### Issue: Ctrl+C doesn't stop the script

**Solution**: The script now handles interrupts gracefully. Press Ctrl+C once and wait a few seconds. If it's in the middle of an API request (30s timeout), it may take up to 30 seconds to stop.

### Issue: "429 Too Many Requests"

**Solution**:
- Reduce `--concurrency` (try 2 or 1)
- Increase rate limit delay in `.env`: `IFIXIT_RATE_LIMIT_RPS=1`
- Use `IFIXIT_API_KEY` if available

### Issue: Some guides have empty content

**Explanation**: Some guides may have minimal content. The script validates:
- Minimum 10 characters
- Title must exist
- Warnings logged for short content

**Solution**: This is expected for some guides. Check the guide on iFixit website to verify.

## Quick Reference

### Most Common Commands

```bash
# Test (dry-run)
python -m scripts.ifixit.collect_ifixit_data --dry-run --max-devices-per-category 2

# Test with database (small sample)
python -m scripts.ifixit.collect_ifixit_data --category Phone --max-devices-per-category 2 --max-guides-per-device 3

# Full extraction
python -m scripts.ifixit.collect_ifixit_data

# Resume interrupted extraction
python -m scripts.ifixit.collect_ifixit_data --resume

# Retry failed devices
python -m scripts.ifixit.collect_ifixit_data --retry-failed
```

### Expected Results

After successful extraction:
- **Equipment Families**: ~16 records (categories)
- **Equipment Models**: ~37,582 records (devices)
- **Knowledge Sources**: ~751,640 records (guides)
- **Storage**: ~1-3GB total (text + metadata)

## Next Steps

After extraction completes:

1. **Generate Embeddings**: Create vector embeddings for RAG search
2. **Index Content**: Set up full-text search indexes
3. **Validate Quality**: Run validation scripts
4. **Monitor Updates**: Set up periodic sync for new guides

## Support

For more information:
- See `OPERATIONS.md` for operational details
- See `TROUBLESHOOTING.md` for common issues
- See `storage_mapping.md` for detailed field mappings
- See `FULL_EXTRACTION_GUIDE.md` for extraction strategies

