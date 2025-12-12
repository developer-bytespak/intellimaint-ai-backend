Plan: One-off script to run chunking per equipment family

Overview
- Script location: `scripts/chunking/family-wise/run_chunk_for_family.py`
- Purpose: For a given `equipment_family.id`, find all `equipment_models` and their `knowledge_sources`, then call the local chunking API `/api/v1/chunk/process` for each `source_id`.

Flow
1. Determine `FAMILY_ID` using (priority): CLI `--family`, environment variable `FAMILY_ID`, or the constant in the script.
2. Connect to Postgres using `DATABASE_URL` (CLI `--db-url` or env var). Query:
   - Get model ids: `SELECT id FROM equipment_models WHERE family_id = %s`.
   - Get source ids: `SELECT id FROM knowledge_sources WHERE model_id = ANY(%s)`
3. For each `source_id`, POST to `{API_URL}/api/v1/chunk/process` with JSON payload `{source_id, dry_run, overwrite}`.
4. Run sequentially (no concurrency) with retry (3 attempts) and exponential backoff.
5. Log successes, responses, and failures to a `failed_sources.txt` file.

Flags
- `--dry-run`: default true (so no DB writes). Use `--no-dry-run` to perform real inserts.
- `--overwrite`: pass overwrite flag to API to replace existing chunks.

Notes
- This is a one-off helper script; it prefers DB lookup because there is no API that lists sources by family.
- Keep runs sequential to make debugging easier.
