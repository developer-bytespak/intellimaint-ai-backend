Run chunking for an equipment family or a single knowledge source

This helper runs the chunking API for `knowledge_sources` associated with an `equipment_family`, or for a single `source_id`.

Files
- `run_chunk_for_family.py` - main script
- `CHUNK_PLAN.md` - plan and flow

Prerequisites
- Python 3.8+
- Install runtime deps:
	```bash
	pip install requests psycopg2-binary python-dotenv
	```

Environment
- `API_URL` - base URL of the running service (default: `http://localhost:8000`)
- `DATABASE_URL` - Postgres DSN used to lookup models and sources (script auto-loads `scripts/.env` if present)

Usage

- Dry-run for a single source (inspect chunks locally; no DB writes):

	```bash
	python run_chunk_for_family.py --source-id 0004ead9-6399-55ec-9341-c2842532232b --dry-run
	```

- Dry-run for a family:

	```bash
	python run_chunk_for_family.py --family <FAMILY_ID> --dry-run
	```

- Real run (calls API to store chunks). Use `--overwrite` to replace existing chunks for a source:

	```bash
	python run_chunk_for_family.py --source-id 0004ead9-6399-55ec-9341-c2842532232b --no-dry-run --overwrite
	```

Notes
- Default behavior is `--dry-run` (no DB writes). Omit `--dry-run` or pass `--no-dry-run` to perform real runs.
- The script will write any failed source ids to `failed_sources.txt` in this folder.
- The script attempts to load `scripts/.env` automatically (via `python-dotenv` or a fallback parser) so you can keep credentials out of the command line.
- Run sequentially for easier debugging; consider adding concurrency if you need higher throughput.
