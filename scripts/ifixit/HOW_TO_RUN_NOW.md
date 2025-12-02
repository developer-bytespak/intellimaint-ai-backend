# How to Run iFixit Data Collection

## Quick Start

### Basic Command (Current Approach)
```bash
python -m scripts.ifixit.collect_ifixit_data
```

This will:
- Extract all categories → devices → guides
- Store everything in your database
- Use the current per-device approach (slower but works)

### Recommended: Test First
```bash
# Test with a small sample (dry-run, no database writes)
python -m scripts.ifixit.collect_ifixit_data \
  --category Mac \
  --max-devices-per-category 2 \
  --max-guides-per-device 5 \
  --dry-run

# If that looks good, run for real
python -m scripts.ifixit.collect_ifixit_data \
  --category Mac \
  --max-devices-per-category 2 \
  --max-guides-per-device 5
```

### Full Extraction (All Categories)
```bash
# Extract everything (will take a long time)
python -m scripts.ifixit.collect_ifixit_data \
  --page-size 200 \
  --concurrency 4
```

## Important Flags

### Speed Optimization
- `--page-size 200` - Use maximum page size (fewer API calls)
- `--concurrency 4` - Process 4 devices at once (adjust based on your system)

### Testing & Limits
- `--category Mac` - Limit to one category
- `--max-devices-per-category 10` - Limit devices (for testing)
- `--max-guides-per-device 5` - Limit guides per device (for testing)
- `--dry-run` - Test without writing to database

### Resume & Recovery
- `--resume` - Continue from where you stopped
- `--retry-failed` - Retry only failed devices

## Example: Extract One Category

```bash
# Extract all Mac devices and guides
python -m scripts.ifixit.collect_ifixit_data \
  --category Mac \
  --page-size 200
```

## Example: Extract Specific Device

```bash
# Extract guides for a specific device
python -m scripts.ifixit.collect_ifixit_data \
  --device "Phone/iPhone/iPhone 14"
```

## What Gets Extracted

✅ **Complete Text Content:**
- Introduction, all steps, conclusion
- All formatting (notes, warnings, tips)
- All images (as markdown URLs)

✅ **All Metadata:**
- Tools, parts, documents
- Author information
- Difficulty, time estimates
- All applicable devices

✅ **All Tables Filled:**
- `equipment_families` (categories)
- `equipment_models` (devices)
- `knowledge_sources` (guides with full content)

## Monitoring Progress

The script will show:
- Devices processed
- Guides processed
- Duplicates skipped
- Errors (if any)

Checkpoints are saved every 50 devices (default) in:
- `scripts/ifixit/checkpoints/checkpoint_*.json`

## Stopping & Resuming

**To Stop:**
- Press `Ctrl+C` once (graceful shutdown)
- Press `Ctrl+C` twice (force exit)

**To Resume:**
```bash
python -m scripts.ifixit.collect_ifixit_data --resume
```

## Current Status

The current approach works but is slower because:
- Queries guides per-device (returns many unrelated guides)
- Hits 10,000 limit per device (safety cap)
- Processes same guides multiple times

**A better approach is being implemented** that will be 1000x faster by querying all guides directly.

For now, you can run the current system - it will work, just take longer.








