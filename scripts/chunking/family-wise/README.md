Run chunking for a single equipment family

This helper script runs the chunking API for every `knowledge_source` associated with a given `equipment_family`.

Files
- `run_chunk_for_family.py` - main script
- `CHUNK_PLAN.md` - plan and flow

Environment
- `API_URL` - base URL of the running service (default: `http://localhost:8000`)
- `DATABASE_URL` - Postgres DSN used to lookup models and sources (if omitted, script will error unless `--db-url` is provided)

Usage

Edit the `FAMILY_ID` constant inside `run_chunk_for_family.py` or pass `--family` to the script.

Dry run (no DB writes):

```bash
python run_chunk_for_family.py --family <FAMILY_ID> --dry-run
```

Real run (writes to DB via API):

```bash
python run_chunk_for_family.py --family <FAMILY_ID> --no-dry-run --overwrite
```

Notes
- The script posts to the chunking endpoint and does not itself write chunks to the DB.
- It runs sequentially and writes failures to `failed_sources.txt` in the same folder.
- Ensure the API is reachable from where you run the script.
