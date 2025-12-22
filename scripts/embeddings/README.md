# Family-wise embeddings via OpenAI Batch API (pgvector)

This folder contains a **script-only** workflow for generating embeddings for existing `knowledge_chunks` in bulk using the **OpenAI Batch API**.

It is intentionally separate from your app’s “regular / realtime” embedding endpoint (for newly uploaded data).

## What it does

For a given `equipment_families.id`:

1. Selects all `knowledge_chunks` under that family where `embedding IS NULL`
2. Splits them into one or more **Batch API** jobs (because large families may exceed batch limits)
3. Saves batch metadata locally to disk (no DB table required)
4. Later: downloads results and writes `knowledge_chunks.embedding` (pgvector) back into Postgres

Mapping back to the DB is done via `custom_id = knowledge_chunks.id`.

## Prerequisites

- Python 3.9+
- Postgres has pgvector enabled and `knowledge_chunks.embedding` is `vector(1536)`
- Environment variables:
  - `DATABASE_URL` (Neon DSN)
  - `OPENAI_API_KEY`

Install deps:

```bash
pip install requests psycopg2-binary python-dotenv
```

## Files created on disk

By default, the script writes to:

```
scripts/embeddings/batches/<family_id>/run_<timestamp>/
  run.json
  batches/
    batch_001/
      input.jsonl
      batch.json
      output.jsonl        (after completion)
      errors.jsonl        (if any)
      failed_chunk_ids.tsv (if any)
    batch_002/
    ...
```

- `run.json` summarizes the run (number of chunks, number of batches).
- Each `batch_###/batch.json` contains `batch_id`, `input_file_id`, etc.

## Usage

### 1) Submit a family

Creates one or more OpenAI batch jobs and writes their IDs to disk:

```bash
python embed_family_batch.py submit --family-id <FAMILY_UUID>
```

Optional knobs:

- `--limit 10000` (debug/smaller runs)
- `--max-requests-per-batch 50000` (default; OpenAI limit)
- `--max-bytes-per-batch 188743680` (default uses safety margin under 200MB)
- `--dry-run` (writes JSONL and metadata but does not call OpenAI)

### 2) Check status

Check all batches under a run directory:

```bash
python embed_family_batch.py status --run-dir ./batches/<family_id>/run_YYYYMMDD_HHMMSS --update-json
```

Or check one batch:

```bash
python embed_family_batch.py status --batch-file ./batches/<family_id>/run_.../batches/batch_001/batch.json
```

### 3) Ingest results into Postgres

When batches are `completed` (or `expired` with partial output), download output JSONL and write embeddings into DB:

```bash
python embed_family_batch.py ingest --run-dir ./batches/<family_id>/run_YYYYMMDD_HHMMSS
```

Options:

- `--dims 1536` (default; matches `vector(1536)`)
- `--update-chunk-size 1000` (how many rows to update per commit)
- `--overwrite` (write embeddings even if already present)
- `--redownload` (download output files again)

### Convenience: submit + poll + ingest (terminal stays open)

```bash
python embed_family_batch.py run --family-id <FAMILY_UUID> --poll-seconds 60
```

## Notes / gotchas

- **Large families** (e.g., “Phone”) may have far more than 50k chunks. This script automatically splits into multiple batch jobs.
- Batch outputs are **not guaranteed to be in the same order** as inputs; the script always maps by `custom_id` (chunk id).
- If some requests fail, the script writes `failed_chunk_ids.tsv` to the batch folder. You can re-run a new `submit` later; since it queries `embedding IS NULL`, successful chunks won’t be re-embedded.
- Batch jobs are async; you **do not** need to keep your laptop open if you use `submit` and later `ingest`.

## Next step in your project

For newly uploaded data (realtime), implement a normal endpoint:

- `POST /api/v1/embed/chunk/{chunk_id}`:
  - loads chunk content from DB
  - calls embeddings synchronously
  - stores `knowledge_chunks.embedding`

Keep that separate from this batch pipeline.
