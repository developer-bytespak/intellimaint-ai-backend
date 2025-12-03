# Safe Extraction Guide - All Guides Approach

## Overview

The all-guides approach now includes **comprehensive safety features** for reliable data extraction:

✅ **Resume capability** - Continue from where you left off  
✅ **Progress tracking** - Track processed guide IDs  
✅ **Checkpoint system** - Periodic snapshots for recovery  
✅ **Error recovery** - Retry failed guides  
✅ **Backup plans** - Multiple safety mechanisms  

---

## How It Works

### 1. Progress Tracking

**File**: `scripts/ifixit/state/all_guides_progress.json`

Tracks:
- ✅ Processed guide IDs (for resume)
- ✅ Failed guide IDs (for retry)
- ✅ Last processed index
- ✅ Statistics (processed, failed, skipped counts)
- ✅ Error messages

**Auto-saved** after each guide is processed.

### 2. Resume Capability

If the script stops (Ctrl+C, crash, network error), you can resume:

```bash
# Resume from last position
python -m scripts.ifixit.collect_ifixit_data --use-all-guides-approach --resume --page-size 200
```

**What happens:**
- Loads `all_guides_progress.json`
- Skips already processed guides
- Continues from last position
- No duplicate processing

### 3. Retry Failed Guides

If some guides fail, retry only the failed ones:

```bash
# Retry only failed guides
python -m scripts.ifixit.collect_ifixit_data --use-all-guides-approach --retry-failed-guides --page-size 200
```

**What happens:**
- Loads failed guide IDs from progress file
- Processes only failed guides
- Clears failed list (re-adds if they fail again)

### 4. Checkpoint System

**Directory**: `scripts/ifixit/checkpoints/`

Periodic JSON snapshots written every N guides (default: 50).

**Contains:**
- Metrics (categories, devices, guides processed)
- Progress ledger state
- Timestamp

**Use for:**
- Recovery if progress file is corrupted
- Monitoring extraction progress
- Debugging issues

---

## Usage Examples

### Full Extraction (First Run)

```bash
# Extract everything with safety features
python -m scripts.ifixit.collect_ifixit_data \
  --use-all-guides-approach \
  --page-size 200 \
  --checkpoint-interval 50
```

**What happens:**
1. Extracts all categories → saves to DB
2. Extracts all devices → saves to DB
3. Fetches all guide summaries
4. Processes each guide → saves immediately
5. Writes progress after each guide
6. Writes checkpoint every 50 guides

### Resume After Interruption

```bash
# Resume from where you left off
python -m scripts.ifixit.collect_ifixit_data \
  --use-all-guides-approach \
  --resume \
  --page-size 200
```

**What happens:**
- Loads progress file
- Skips already processed guides
- Continues from last position
- Processes remaining guides

### Retry Failed Guides

```bash
# Retry only failed guides
python -m scripts.ifixit.collect_ifixit_data \
  --use-all-guides-approach \
  --retry-failed-guides \
  --page-size 200
```

**What happens:**
- Loads failed guide IDs
- Processes only failed guides
- Updates progress file

### Test Run (Small Sample)

```bash
# Test with small sample first
python -m scripts.ifixit.collect_ifixit_data \
  --use-all-guides-approach \
  --max-guides-per-device 100 \
  --page-size 200 \
  --dry-run
```

---

## Safety Features

### 1. Immediate Database Saves

- ✅ Categories saved immediately (Step 1)
- ✅ Devices saved immediately (Step 1)
- ✅ Guides saved immediately (Step 3, per guide)

**No batching** - data is saved as soon as it's processed.

### 2. Progress Persistence

- ✅ Progress saved after each guide
- ✅ Atomic writes (temp file → rename)
- ✅ Thread-safe (locks for concurrent access)

### 3. Error Handling

- ✅ Failed guides tracked separately
- ✅ Errors logged with context
- ✅ Processing continues on errors
- ✅ Failed guides can be retried

### 4. Checkpoint System

- ✅ Periodic snapshots
- ✅ Contains full state
- ✅ Recovery option if progress file lost

### 5. Resume Support

- ✅ Tracks processed guide IDs
- ✅ Skips already processed
- ✅ Continues from last position
- ✅ No duplicate processing

---

## Progress File Structure

**File**: `scripts/ifixit/state/all_guides_progress.json`

```json
{
  "processed_guide_ids": [1, 2, 3, ...],
  "last_guide_index": 5000,
  "total_guides_fetched": 50000,
  "guides_processed": 4500,
  "guides_skipped": 500,
  "errors": ["Guide 123: API timeout", ...],
  "failed_guide_ids": [123, 456, ...],
  "start_time": "2024-01-01T12:00:00Z",
  "last_updated": "2024-01-01T13:00:00Z"
}
```

---

## Backup Plans

### Plan 1: Resume (Recommended)

If script stops:
1. Wait for current guide to finish saving
2. Run with `--resume` flag
3. Continues from last position

### Plan 2: Retry Failed

If some guides fail:
1. Check progress file for failed IDs
2. Run with `--retry-failed-guides`
3. Only failed guides are retried

### Plan 3: Checkpoint Recovery

If progress file is corrupted:
1. Find latest checkpoint in `checkpoints/` directory
2. Manually restore progress (if needed)
3. Resume from checkpoint position

### Plan 4: Database Verification

Verify what's in database:
```bash
python -m scripts.ifixit.verify_extraction.py
```

Shows:
- Total guides in database
- Content statistics
- Metadata completeness

---

## Best Practices

### 1. Start with Test Run

```bash
# Test with small sample
python -m scripts.ifixit.collect_ifixit_data \
  --use-all-guides-approach \
  --max-guides-per-device 100 \
  --dry-run
```

### 2. Monitor Progress

Watch the logs for:
- Progress percentage
- Failed guides count
- Checkpoint writes

### 3. Use Checkpoints

Set appropriate checkpoint interval:
```bash
--checkpoint-interval 100  # Write checkpoint every 100 guides
```

### 4. Handle Interruptions

If script stops:
- Don't panic - progress is saved
- Use `--resume` to continue
- Check logs for errors

### 5. Retry Failed Guides

After full run:
- Check for failed guides
- Retry with `--retry-failed-guides`
- Monitor for persistent failures

---

## Troubleshooting

### Progress File Not Found

**Issue**: `all_guides_progress.json` doesn't exist

**Solution**: This is normal for first run. File will be created automatically.

### Resume Not Working

**Issue**: Resume starts from beginning

**Solution**: 
- Check if progress file exists
- Verify file has `processed_guide_ids`
- Check logs for "Resume mode" message

### Too Many Failed Guides

**Issue**: Many guides failing

**Solution**:
- Check network connection
- Verify API rate limits
- Check error messages in progress file
- Retry with `--retry-failed-guides`

### Database Connection Lost

**Issue**: Database errors during extraction

**Solution**:
- Progress is still saved
- Resume after fixing database
- Failed guides will be retried

---

## Summary

The all-guides approach now has **comprehensive safety features**:

✅ **Resume** - Continue from last position  
✅ **Progress Tracking** - Track processed guides  
✅ **Checkpoints** - Periodic snapshots  
✅ **Error Recovery** - Retry failed guides  
✅ **Immediate Saves** - No data loss  
✅ **Backup Plans** - Multiple recovery options  

**Safe to use for production extraction!** 🚀







