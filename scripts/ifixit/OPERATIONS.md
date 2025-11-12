## iFixit Collector Operations Guide

### Running the Collector
- Activate your Python environment inside `intellimaint-ai-backend/scripts` and install requirements (`pip install -r scripts/requirements.txt` if needed).
- Execute the collector as a module to ensure relative imports resolve:
  - `py -m scripts.ifixit.collect_ifixit_data`
- Useful flags:
  - `--category Appliance` limit to a top-level category.
  - `--device "Phone/iPhone/iPhone 4"` process a specific device.
  - `--resume` continue from the last CSV ledger state.
  - `--retry-failed` re-run devices recorded as failed.
  - `--dry-run` fetch data without writing to the database.
  - `--log-format json` switch to JSON logs for pipelines or log aggregation.
  - `--checkpoint-interval 0` disable checkpoint snapshots (default is 50 devices).

### Storage & Progress Tracking
- Progress ledger: `scripts/ifixit/state/ingest_state.csv` (auto-created). Tracks category status, last device index, last guide id, retry counts, and failed devices.
- Checkpoints: `scripts/ifixit/checkpoints/checkpoint_*.json` snapshots every `N` processed devices (default 50) containing metrics + ledger export.
- Failure report: `scripts/ifixit/state/failed_devices.json` refreshed after each run; lists unresolved failures for quick triage or `--retry-failed` runs.

### Resume & Retry Workflow
1. Normal run creates CSV ledger entries and checkpoints automatically.
2. If the process stops early, rerun with `--resume` to continue from the recorded cursor (skips completed devices).
3. If devices failed, run with `--retry-failed` to reprocess only the recorded failed paths. Successful retries are removed from the ledger’s `failed_devices` list.
4. Delete `state/ingest_state.csv` if you need a clean slate.

### Observability
- Default logs are human-readable; use `--log-format json` for structured pipelines.
- Device and category completions emit structured log events (`event=device_complete`, `event=device_failed`, `event=category_complete`) to simplify downstream parsing.
- `scripts/ifixit/checkpoints/` and `failed_devices.json` offer offline snapshots for incident review.

### Safety Tips
- The collector never downloads images—only textual content and metadata are persisted.
- Database writes rely on deterministic UUIDs; reruns safely upsert existing rows.
- Use `--dry-run` with filters to audit the scope before running a full ingestion.

