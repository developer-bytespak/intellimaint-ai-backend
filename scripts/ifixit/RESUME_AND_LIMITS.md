# Resume Behavior and Guide Limits

## Guide Limit Issue (FIXED)

### Problem
The collector was showing "Processing guide X/1000" because it had a hardcoded limit of 10 pages × 100 guides = 1000 guides per device.

### Solution
✅ **Removed the hard limit** - Now fetches ALL available guides for each device.

The pagination will stop naturally when:
- API returns fewer items than page size (end of results)
- API provides a total count and we reach it
- Safety limit of 10,000 items (only if total is unknown - prevents infinite loops)

### What Changed
- **Before**: `max_pages=10` (1000 guides max per device)
- **After**: `max_pages=None` (fetches all available guides)

---

## Resume and Overwrite Behavior

### How Resume Works

The collector uses **upserts** (INSERT ... ON CONFLICT DO UPDATE), which means:

1. **No Duplicates**: Same guide ID = same UUID = same database record
2. **Safe to Re-run**: Running again won't create duplicate records
3. **Updates Existing**: If a guide already exists, it will be updated (content, metadata, etc.)

### Resume Options

#### Option 1: Resume from Last Position (`--resume`)
```bash
python -m scripts.ifixit.collect_ifixit_data --resume
```

**What it does:**
- Loads progress from `scripts/ifixit/state/ingest_state.csv`
- Skips **completed categories** (status = "complete")
- Continues from last device index for in-progress categories
- **Does NOT skip individual guides** - will re-process all guides for devices that weren't completed

**Example:**
- Category "Mac" was processing device #5 when stopped
- Resume will start from device #6
- But device #5's guides will be re-processed (safely upserted, no duplicates)

#### Option 2: Normal Run (No Resume)
```bash
python -m scripts.ifixit.collect_ifixit_data
```

**What it does:**
- Starts from beginning
- Re-processes everything
- **Safe** - uses upserts, so no duplicates created
- **Updates** existing records with latest content/metadata

#### Option 3: Retry Failed Only (`--retry-failed`)
```bash
python -m scripts.ifixit.collect_ifixit_data --retry-failed
```

**What it does:**
- Only re-processes devices that failed
- Skips successful devices

---

## What Happens When You Re-run?

### Scenario: You processed 218 guides, then stop and run again

**Without `--resume`:**
- ✅ Starts from beginning
- ✅ Re-processes all 218 guides (and any new ones)
- ✅ **No duplicates** - same UUID = same record
- ✅ **Updates** existing guides with latest content
- ⚠️ Takes time (re-fetches from API)

**With `--resume`:**
- ✅ Continues from where it stopped
- ✅ Skips completed categories/devices
- ✅ Re-processes guides for in-progress devices (safely upserted)
- ✅ Faster (skips already-completed work)

### Database Behavior

**Upsert Logic:**
```sql
INSERT INTO knowledge_sources (id, title, raw_content, ...)
VALUES (...)
ON CONFLICT (id) DO UPDATE
SET title = EXCLUDED.title,
    raw_content = EXCLUDED.raw_content,
    metadata = EXCLUDED.metadata,
    updated_at = NOW();
```

**This means:**
- ✅ Same guide ID → Same UUID → Same record
- ✅ Re-running updates the record (doesn't create duplicate)
- ✅ Latest content/metadata is saved
- ✅ `updated_at` timestamp is updated

---

## Recommendations

### If You Want to Continue from Where You Stopped:
```bash
python -m scripts.ifixit.collect_ifixit_data --resume
```

### If You Want to Re-process Everything (e.g., after code changes):
```bash
python -m scripts.ifixit.collect_ifixit_data
# No --resume flag - will re-process all, but safely (no duplicates)
```

### If You Want a Clean Start:
1. Delete progress file: `rm scripts/ifixit/state/ingest_state.csv`
2. Run normally: `python -m scripts.ifixit.collect_ifixit_data`
3. Database records will be updated (not duplicated)

---

## Progress Tracking

The system tracks progress in:
- **CSV File**: `scripts/ifixit/state/ingest_state.csv`
  - Tracks: category status, last device, last guide ID, counts
  - Used for resume functionality

- **Checkpoints**: `scripts/ifixit/checkpoints/checkpoint_*.json`
  - Snapshots every N devices (default: 50)
  - Contains metrics and full ledger export

---

## Summary

✅ **No Duplicates**: Upserts prevent duplicate records  
✅ **Safe to Re-run**: Can run multiple times without issues  
✅ **Resume Available**: Use `--resume` to continue from last position  
✅ **All Guides**: Now fetches ALL available guides (no 1000 limit)  
✅ **Updates Existing**: Re-running updates existing records with latest data  

**Best Practice**: Use `--resume` if you want to continue from where you stopped. Otherwise, re-running is safe but will re-process everything.



