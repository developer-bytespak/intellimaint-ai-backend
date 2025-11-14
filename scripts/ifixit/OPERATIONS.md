## iFixit Collector Operations Guide

### Prerequisites
- Python 3.8+ with required packages installed (`pip install -r scripts/requirements.txt`)
- Database connection configured via `DATABASE_URL` environment variable
- Optional: `IFIXIT_API_KEY` for higher rate limits (not required, API works without it)

### Running the Collector
- Activate your Python environment and navigate to the project root.
- Execute the collector as a module to ensure relative imports resolve:
  - `python -m scripts.ifixit.collect_ifixit_data`
  - Or from project root: `py -m scripts.ifixit.collect_ifixit_data`
- Useful flags:
  - `--category Appliance` limit to a top-level category (can specify multiple times).
  - `--device "Phone/iPhone/iPhone 4"` process a specific device path (can specify multiple times).
  - `--device-filter "iPhone"` process only devices whose path contains the substring.
  - `--resume` continue from the last CSV ledger state.
  - `--retry-failed` re-run devices recorded as failed.
  - `--dry-run` fetch data without writing to the database (recommended for first test).
  - `--log-format json` switch to JSON logs for pipelines or log aggregation.
  - `--log-level DEBUG` set logging verbosity (DEBUG, INFO, WARNING, ERROR).
  - `--checkpoint-interval 0` disable checkpoint snapshots (default is 50 devices).
  - `--concurrency 4` set number of concurrent device processing threads (default: 4).
  - `--max-devices-per-category 10` limit devices per category (useful for testing).
  - `--max-guides-per-device 5` limit guides per device (useful for testing).

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
- Enhanced error messages include context (device path, guide ID, category) for easier debugging.

### Content Extraction Features
- **Comprehensive Guide Content**: Extracts all text content including:
  - Introduction and conclusion
  - All step instructions with proper formatting
  - Notes, warnings, cautions, and tips (formatted as markdown blockquotes)
  - Bullet points with proper indentation
- **Rich Metadata**: Captures:
  - Guide-level tools and parts
  - Step-level images (as URLs, not binaries)
  - Author information
  - Difficulty ratings and time estimates
  - Flags, prerequisites, and documents
  - Full API response data for future reference
- **Content Validation**: Automatically validates content before insertion:
  - Minimum content length check (10 characters)
  - Title validation
  - Warnings for incomplete data

### Safety Tips
- The collector never downloads images—only textual content and metadata are persisted.
- Database writes rely on deterministic UUIDs; reruns safely upsert existing rows.
- Use `--dry-run` with filters to audit the scope before running a full ingestion.
- Content validation prevents empty or invalid guides from being stored.
- Enhanced error handling provides clear context for troubleshooting failures.

### Testing Before Full Run
1. Test API connectivity: `python -m scripts.ifixit.test_api_structure`
2. Run discovery: `python -m scripts.ifixit.discover_devices`
3. Test with dry-run: `python -m scripts.ifixit.collect_ifixit_data --dry-run --max-devices-per-category 2 --max-guides-per-device 2`
4. Validate extracted data quality using validation scripts

