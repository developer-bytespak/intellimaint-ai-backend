# Full iFixit Manual Extraction Guide

This guide will help you extract all ~751,640 guides from 37,582 devices and store them in your database.

## Prerequisites

1. **Database Setup**:
   - Ensure `DATABASE_URL` is set in your `.env` file
   - Format: `postgresql://user:password@host:port/database`
   - Verify database connection works

2. **Python Environment**:
   - Install dependencies: `pip install -r scripts/requirements.txt`
   - Ensure Python 3.8+ is available

3. **Verify API Access**:
   - Test API connectivity: `python -m scripts.ifixit.test_api_structure`
   - Should complete without errors

## Recommended Approach: Incremental Extraction

Given the large volume (751K+ guides), extract in stages:

### Option 1: Extract by Category (Recommended)

Extract one category at a time to monitor progress and handle issues:

```bash
# Start with a smaller category for testing
python -m scripts.ifixit.collect_ifixit_data --category Phone --dry-run

# If dry-run looks good, run for real
python -m scripts.ifixit.collect_ifixit_data --category Phone

# Then continue with other categories
python -m scripts.ifixit.collect_ifixit_data --category Camera
python -m scripts.ifixit.collect_ifixit_data --category Tablet
# ... and so on
```

### Option 2: Full Extraction (All Categories)

Run the full extraction (will take days/weeks):

```bash
# Start full extraction
python -m scripts.ifixit.collect_ifixit_data

# The script will:
# - Process all 16 top-level categories
# - Extract all 37,582 devices
# - Extract all guides for each device
# - Store everything in the database
# - Create progress checkpoints every 50 devices
# - Allow resuming with --resume flag
```

## Running Full Extraction

### Step 1: Test with Small Sample First

```bash
# Test with 2 devices, 2 guides each
python -m scripts.ifixit.collect_ifixit_data \
  --dry-run \
  --max-devices-per-category 2 \
  --max-guides-per-device 2 \
  --category Phone
```

Verify the output looks correct, then proceed.

### Step 2: Run Full Extraction

```bash
# Full extraction with progress tracking
python -m scripts.ifixit.collect_ifixit_data \
  --log-level INFO \
  --log-format text \
  --checkpoint-interval 50 \
  --concurrency 4
```

**Parameters explained:**
- `--log-level INFO`: Show progress information
- `--log-format text`: Human-readable logs (use `json` for log aggregation)
- `--checkpoint-interval 50`: Save progress every 50 devices (default)
- `--concurrency 4`: Process 4 devices simultaneously (adjust based on rate limits)

### Step 3: Monitor Progress

The script will:
- Show progress in logs
- Create checkpoints in `scripts/ifixit/checkpoints/`
- Track progress in `scripts/ifixit/state/ingest_state.csv`
- Generate failure reports in `scripts/ifixit/state/failed_devices.json`

### Step 4: Resume if Interrupted

If the process stops (network issue, crash, etc.):

```bash
# Resume from last checkpoint
python -m scripts.ifixit.collect_ifixit_data --resume
```

### Step 5: Retry Failed Devices

After completion, retry any failed devices:

```bash
# Retry only failed devices
python -m scripts.ifixit.collect_ifixit_data --retry-failed
```

## Time Estimates

Based on the discovery results:
- **Total Devices**: 37,582
- **Estimated Guides**: 751,640
- **Average Guides per Device**: 20

**Estimated Time** (with 4 concurrent workers, 2 requests/second):
- Per device: ~10 seconds (fetching guides + detail)
- Total time: ~37,582 devices × 10s = ~375,820 seconds = **~104 hours = ~4.3 days**

**Note**: Actual time depends on:
- Network speed
- API rate limits
- Database write speed
- Number of guides per device (varies)

## Optimization Tips

### 1. Increase Concurrency (if rate limits allow)

```bash
# Process 8 devices concurrently (if API allows)
python -m scripts.ifixit.collect_ifixit_data --concurrency 8
```

### 2. Process Categories Separately

Run multiple terminal sessions, each processing a different category:

```bash
# Terminal 1
python -m scripts.ifixit.collect_ifixit_data --category Phone

# Terminal 2
python -m scripts.ifixit.collect_ifixit_data --category Camera

# Terminal 3
python -m scripts.ifixit.collect_ifixit_data --category Tablet
```

### 3. Use Screen/Tmux for Long-Running Jobs

```bash
# Start a screen session
screen -S ifixit-extraction

# Run the extraction
python -m scripts.ifixit.collect_ifixit_data

# Detach: Ctrl+A, then D
# Reattach: screen -r ifixit-extraction
```

### 4. Monitor Database Size

Keep an eye on database growth:

```sql
-- Check knowledge sources count
SELECT COUNT(*) FROM knowledge_sources WHERE source_type = 'ifixit';

-- Check database size
SELECT pg_size_pretty(pg_database_size(current_database()));
```

## Monitoring Progress

### Check Progress Files

```bash
# View progress ledger
cat scripts/ifixit/state/ingest_state.csv

# View latest checkpoint
ls -lt scripts/ifixit/checkpoints/ | head -1

# View failed devices
cat scripts/ifixit/state/failed_devices.json
```

### Query Database for Progress

```sql
-- Count extracted guides
SELECT COUNT(*) as total_guides 
FROM knowledge_sources 
WHERE source_type = 'ifixit';

-- Count by category (via equipment families)
SELECT ef.name, COUNT(DISTINCT em.id) as devices, COUNT(ks.id) as guides
FROM equipment_families ef
LEFT JOIN equipment_models em ON em.family_id = ef.id
LEFT JOIN knowledge_sources ks ON ks.model_id = em.id AND ks.source_type = 'ifixit'
GROUP BY ef.name
ORDER BY guides DESC;
```

## Validation After Extraction

After extraction completes, validate the data:

```bash
# Run validation script
python -m scripts.ifixit.validate_extraction

# This will check:
# - All families have proper metadata
# - All models are linked correctly
# - All guides have content
# - All relationships are valid
```

## Troubleshooting

### If Rate Limited

- Reduce `--concurrency` (try 2 or 1)
- Increase rate limit delay in `scripts/ifixit/config.py`
- Consider using `IFIXIT_API_KEY` if available

### If Database Errors

- Check database connection
- Verify schema matches Prisma schema
- Check database disk space
- Review database logs

### If Process Crashes

- Use `--resume` to continue
- Check `failed_devices.json` for issues
- Review logs for error patterns
- Retry failed devices with `--retry-failed`

## Expected Database Growth

- **Equipment Families**: ~16 records (top-level categories)
- **Equipment Models**: ~37,582 records (devices)
- **Knowledge Sources**: ~751,640 records (guides)
- **Estimated Storage**: 
  - Text content: ~500MB-2GB (depending on guide length)
  - Metadata: ~500MB-1GB (JSON)
  - Total: ~1-3GB for all guides

## Next Steps After Extraction

1. **Generate Embeddings**: Create vector embeddings for RAG
2. **Index Content**: Set up search/indexing
3. **Validate Quality**: Run validation scripts
4. **Monitor Updates**: Set up periodic sync for new guides

## Quick Start Command

For immediate full extraction:

```bash
python -m scripts.ifixit.collect_ifixit_data \
  --log-level INFO \
  --checkpoint-interval 50 \
  --concurrency 4
```

This will start extracting all manuals and store them in your database. The process is resumable, so you can stop and restart it anytime.

