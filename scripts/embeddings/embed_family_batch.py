#!/usr/bin/env python3
"""
Batch-embed KnowledgeChunks for a given EquipmentFamily using OpenAI Batch API,
then ingest the results back into Postgres (pgvector).

Designed to work with the schema:

- equipment_families -> equipment_models -> knowledge_sources -> knowledge_chunks

Key idea:
- SUBMIT: create one or more OpenAI batch jobs (JSONL input files) for all chunks in a family
          where knowledge_chunks.embedding IS NULL.
- INGEST: download batch output JSONL and update knowledge_chunks.embedding using custom_id=chunk_id.

State is stored locally on disk (no DB tables required).

Requirements:
- Python 3.9+
- requests, psycopg2-binary, python-dotenv (optional)
- Env:
  - DATABASE_URL (or --db-url)
  - OPENAI_API_KEY

References:
- Batch API guide: https://platform.openai.com/docs/guides/batch
- Batch create:     https://platform.openai.com/docs/api-reference/batch/create
- Files API:        https://platform.openai.com/docs/api-reference/files
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple
from urllib3.exceptions import ProtocolError

# Optional dotenv support (matches style in your other scripts)
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    load_dotenv = None  # type: ignore

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore

try:
    from requests.adapters import HTTPAdapter  # type: ignore
    from urllib3.util.retry import Retry  # type: ignore
except Exception:  # pragma: no cover
    HTTPAdapter = None  # type: ignore
    Retry = None  # type: ignore
try:
    import psycopg2  # type: ignore
    from psycopg2.extras import RealDictCursor, execute_values, register_uuid  # type: ignore
except Exception:  # pragma: no cover
    psycopg2 = None  # type: ignore

DEFAULT_MODEL = "text-embedding-3-small"
DEFAULT_ENDPOINT = "https://api.openai.com"
DEFAULT_MAX_REQUESTS_PER_BATCH = 50_000
# Batch file max is 200MB; keep a margin for safety
DEFAULT_MAX_BYTES_PER_BATCH = 180 * 1024 * 1024

LOG = logging.getLogger("embed_family_batch")


@dataclass(frozen=True)
class ChunkRow:
    chunk_id: str
    content: str


def _require_requests() -> None:
    if requests is None:
        raise RuntimeError("requests is required. Install with: pip install requests")


def _require_psycopg2() -> None:
    if psycopg2 is None:
        raise RuntimeError("psycopg2 is required. Install with: pip install psycopg2-binary")


def _utc_now_compact() -> str:
    return _dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _json_dumps_compact(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _openai_headers(api_key: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _openai_post_file(api_base: str, api_key: str, file_path: Path, purpose: str = "batch") -> Dict:
    """
    POST /v1/files multipart upload.

    Returns the file object JSON.
    """
    _require_requests()
    url = api_base.rstrip("/") + "/v1/files"

    # Use a Session with urllib3 Retry for idempotent/network errors and
    # also perform an outer retry loop to handle chunked/streaming errors
    sess = requests.Session()
    # Configure urllib3 Retry if available
    if Retry is not None and HTTPAdapter is not None:
        retries = Retry(total=3, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504))
        sess.mount("https://", HTTPAdapter(max_retries=retries))

    attempts = 4
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            with file_path.open("rb") as f:
                files = {"file": (file_path.name, f)}
                data = {"purpose": purpose}
                resp = sess.post(url, headers=_openai_headers(api_key), data=data, files=files, timeout=600)
            if resp.status_code < 300:
                return resp.json()

            # Treat 5xx as retryable; other errors are fatal
            if 500 <= resp.status_code < 600:
                last_exc = RuntimeError(f"OpenAI file upload failed: {resp.status_code} {resp.text[:2000]}")
            else:
                raise RuntimeError(f"OpenAI file upload failed: {resp.status_code} {resp.text[:2000]}")

        except Exception as e:
            # Capture exceptions (network, chunked encoding, timeouts, etc.) and retry
            last_exc = e

        # If we'll retry, sleep with exponential backoff
        if attempt < attempts:
            sleep = 2 ** attempt
            time.sleep(sleep)

    raise RuntimeError("File upload failed after retries") from last_exc


def _openai_create_batch(api_base: str, api_key: str, input_file_id: str, endpoint: str) -> Dict:
    """
    POST /v1/batches
    """
    _require_requests()
    url = api_base.rstrip("/") + "/v1/batches"
    body = {
        "input_file_id": input_file_id,
        "endpoint": endpoint,
        "completion_window": "24h",
    }
    resp = requests.post(url, headers={**_openai_headers(api_key), "Content-Type": "application/json"}, json=body, timeout=60)
    if resp.status_code >= 300:
        raise RuntimeError(f"OpenAI create batch failed: {resp.status_code} {resp.text[:2000]}")
    return resp.json()


def _openai_get_batch(api_base: str, api_key: str, batch_id: str) -> Dict:
    """
    GET /v1/batches/{id}
    """
    _require_requests()
    url = api_base.rstrip("/") + f"/v1/batches/{batch_id}"
    resp = requests.get(url, headers=_openai_headers(api_key), timeout=60)
    if resp.status_code >= 300:
        raise RuntimeError(f"OpenAI get batch failed: {resp.status_code} {resp.text[:2000]}")
    return resp.json()


def _openai_download_file_content(api_base: str, api_key: str, file_id: str, out_path: Path) -> None:
    _require_requests()
    url = api_base.rstrip("/") + f"/v1/files/{file_id}/content"
    sess = requests.Session()
    retries = Retry(total=3, backoff_factor=2, status_forcelist=(429,500,502,503,504))
    sess.mount("https://", HTTPAdapter(max_retries=retries))

    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    max_attempts = 4
    for attempt in range(1, max_attempts + 1):
        try:
            with sess.get(url, headers=_openai_headers(api_key), stream=True, timeout=(10, 600)) as resp:
                resp.raise_for_status()
                with tmp_path.open("wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024*1024):
                        if chunk:
                            f.write(chunk)
            tmp_path.replace(out_path)
            return
        except (requests.exceptions.ChunkedEncodingError,
                requests.exceptions.ConnectionError,
                ProtocolError,
                requests.exceptions.RequestException) as e:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            if attempt == max_attempts:
                raise RuntimeError(f"Failed to download file {file_id}") from e
            time.sleep(2 ** attempt)


def _connect_db(db_url: str):
    _require_psycopg2()
    conn = psycopg2.connect(db_url, sslmode="require")
    try:
        register_uuid(conn_or_curs=conn)  # type: ignore[arg-type]
    except Exception:
        pass
    return conn


def _select_unembedded_chunks_for_family(conn, family_id: str, limit: Optional[int] = None) -> List[ChunkRow]:
    """
    Select chunks for a family with embedding IS NULL.

    This uses a direct join path:
        equipment_models.family_id -> knowledge_sources.model_id -> knowledge_chunks.source_id
    """
    sql = """
        SELECT kc.id AS chunk_id, kc.content AS content
        FROM knowledge_chunks kc
        JOIN knowledge_sources ks ON ks.id = kc.source_id
        JOIN equipment_models em ON em.id = ks.model_id
        WHERE em.family_id = %s
          AND kc.embedding IS NULL
        ORDER BY kc.created_at ASC, kc.chunk_index ASC
    """
    params: Tuple = (family_id,)
    if limit is not None:
        sql += " LIMIT %s"
        params = (family_id, limit)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [ChunkRow(chunk_id=str(r["chunk_id"]), content=str(r["content"])) for r in rows]


def _iter_batches_by_limits(
    chunks: Sequence[ChunkRow],
    model: str,
    max_requests: int,
    max_bytes: int,
) -> Iterator[List[Tuple[ChunkRow, str]]]:
    """
    Split chunks into multiple batch files.

    Yields lists of (ChunkRow, jsonl_line) while respecting:
    - max_requests (OpenAI batch limit)
    - max_bytes    (OpenAI file size limit; we keep a safety margin)
    """
    current: List[Tuple[ChunkRow, str]] = []
    current_bytes = 0

    for row in chunks:
        req_obj = {
            "custom_id": row.chunk_id,
            "method": "POST",
            "url": "/v1/embeddings",
            "body": {
                "model": model,
                "input": row.content,
                # Optional: keep floats (default) for easiest DB ingestion
                "encoding_format": "float",
            },
        }
        line = _json_dumps_compact(req_obj) + "\n"
        line_bytes = len(line.encode("utf-8"))

        # Start a new batch if adding this line would break limits
        if current and (len(current) >= max_requests or (current_bytes + line_bytes) > max_bytes):
            yield current
            current = []
            current_bytes = 0

        current.append((row, line))
        current_bytes += line_bytes

    if current:
        yield current


def _write_json(path: Path, data: Dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def cmd_submit(args: argparse.Namespace) -> int:
    api_key = args.openai_api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        LOG.error("OPENAI_API_KEY must be set (or pass --openai-api-key)")
        return 2

    db_url = args.db_url or os.environ.get("DATABASE_URL")
    if not db_url:
        LOG.error("DATABASE_URL must be set (or pass --db-url)")
        return 2

    family_id = args.family_id
    run_dir = Path(args.out_dir) / family_id / f"run_{_utc_now_compact()}"
    batches_dir = run_dir / "batches"
    _ensure_dir(batches_dir)

    LOG.info("Selecting unembedded chunks for family_id=%s ...", family_id)
    conn = _connect_db(db_url)
    try:
        chunks = _select_unembedded_chunks_for_family(conn, family_id, limit=args.limit)
    finally:
        conn.close()

    LOG.info("Found %d chunks with embedding IS NULL.", len(chunks))
    if not chunks:
        _write_json(run_dir / "run.json", {
            "family_id": family_id,
            "model": args.model,
            "created_at_utc": _dt.datetime.utcnow().isoformat() + "Z",
            "db_limit": args.limit,
            "num_chunks": 0,
            "note": "No chunks found requiring embeddings (embedding IS NULL).",
        })
        LOG.info("Nothing to do. Created %s", run_dir)
        return 0

    # Create batch files and jobs
    batch_idx = 0
    created_batches: List[Dict] = []

    for group in _iter_batches_by_limits(
        chunks=chunks,
        model=args.model,
        max_requests=args.max_requests_per_batch,
        max_bytes=args.max_bytes_per_batch,
    ):
        batch_idx += 1
        batch_name = f"batch_{batch_idx:03d}"
        batch_dir = batches_dir / batch_name
        _ensure_dir(batch_dir)

        input_path = batch_dir / "input.jsonl"
        with input_path.open("w", encoding="utf-8") as f:
            for _, line in group:
                f.write(line)

        LOG.info("Uploading %s (%d requests) ...", input_path, len(group))
        if args.dry_run:
            batch_meta = {
                "dry_run": True,
                "batch_id": None,
                "input_file_id": None,
                "endpoint": "/v1/embeddings",
                "model": args.model,
                "family_id": family_id,
                "num_requests": len(group),
                "input_jsonl": str(input_path),
                "created_at_utc": _dt.datetime.utcnow().isoformat() + "Z",
            }
            _write_json(batch_dir / "batch.json", batch_meta)
            created_batches.append(batch_meta)
            continue

        file_obj = _openai_post_file(args.api_base, api_key, input_path, purpose="batch")
        input_file_id = file_obj["id"]

        batch_obj = _openai_create_batch(args.api_base, api_key, input_file_id=input_file_id, endpoint="/v1/embeddings")
        batch_id = batch_obj["id"]

        batch_meta = {
            "dry_run": False,
            "batch_id": batch_id,
            "input_file_id": input_file_id,
            "endpoint": "/v1/embeddings",
            "model": args.model,
            "family_id": family_id,
            "num_requests": len(group),
            "input_jsonl": str(input_path),
            "created_at_utc": _dt.datetime.utcnow().isoformat() + "Z",
            "openai_batch_object": batch_obj,
        }
        _write_json(batch_dir / "batch.json", batch_meta)
        created_batches.append(batch_meta)

        LOG.info("Created OpenAI batch: %s (saved %s)", batch_id, batch_dir / "batch.json")

        # Optional throttling between creations
        if args.sleep_between_batches > 0:
            time.sleep(args.sleep_between_batches)

    run_meta = {
        "family_id": family_id,
        "model": args.model,
        "created_at_utc": _dt.datetime.utcnow().isoformat() + "Z",
        "db_limit": args.limit,
        "num_chunks": len(chunks),
        "num_batches": batch_idx,
        "batches": [
            {
                "batch_dir": str((batches_dir / f"batch_{i+1:03d}").resolve()),
                "batch_id": created_batches[i].get("batch_id"),
                "num_requests": created_batches[i].get("num_requests"),
            }
            for i in range(batch_idx)
        ],
        "notes": {
            "max_requests_per_batch": args.max_requests_per_batch,
            "max_bytes_per_batch": args.max_bytes_per_batch,
            "dry_run": args.dry_run,
        },
    }
    _write_json(run_dir / "run.json", run_meta)

    LOG.info("Done. Run directory: %s", run_dir.resolve())
    return 0


def _iter_batch_json_paths(run_dir: Path) -> List[Path]:
    batches_dir = run_dir / "batches"
    if not batches_dir.exists():
        raise FileNotFoundError(f"batches directory not found: {batches_dir}")
    return sorted(p for p in batches_dir.glob("batch_*/batch.json"))


def cmd_status(args: argparse.Namespace) -> int:
    api_key = args.openai_api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        LOG.error("OPENAI_API_KEY must be set (or pass --openai-api-key)")
        return 2

    targets: List[Path] = []
    if args.batch_file:
        targets = [Path(args.batch_file)]
    elif args.run_dir:
        targets = _iter_batch_json_paths(Path(args.run_dir))
    else:
        LOG.error("Provide --batch-file or --run-dir")
        return 2

    for batch_json_path in targets:
        meta = _read_json(batch_json_path)
        batch_id = meta.get("batch_id")
        if not batch_id:
            LOG.info("%s: dry_run or missing batch_id", batch_json_path)
            continue

        batch_obj = _openai_get_batch(args.api_base, api_key, batch_id=batch_id)
        status = batch_obj.get("status")
        out_file = batch_obj.get("output_file_id")
        err_file = batch_obj.get("error_file_id")
        counts = batch_obj.get("request_counts")
        LOG.info("Batch %s | status=%s | output=%s | error=%s | counts=%s",
                 batch_id, status, out_file, err_file, counts)

        # Optionally update batch.json with latest OpenAI object
        if args.update_json:
            meta["openai_batch_object_latest"] = batch_obj
            meta["status_latest"] = status
            meta["updated_at_utc"] = _dt.datetime.utcnow().isoformat() + "Z"
            _write_json(batch_json_path, meta)

    return 0


def _parse_output_jsonl(path: Path) -> Iterator[Tuple[str, Optional[List[float]], Optional[str]]]:
    """
    Yields (chunk_id, embedding, error_message).

    The output file is JSONL. Each line looks like:
    {
      "custom_id": "...",
      "response": { "status_code": 200, "body": { "data": [ {"embedding": [...]} ] } }
    }
    or may contain an "error" section if request failed.
    """
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception as e:
                yield ("", None, f"line {line_no}: invalid json: {e}")
                continue

            chunk_id = obj.get("custom_id", "")
            if not chunk_id:
                yield ("", None, f"line {line_no}: missing custom_id")
                continue

            resp = obj.get("response")
            err = obj.get("error")

            if err and not resp:
                yield (chunk_id, None, _json_dumps_compact(err)[:2000])
                continue

            if not resp:
                yield (chunk_id, None, f"line {line_no}: missing response")
                continue

            status_code = resp.get("status_code")
            body = resp.get("body", {})

            if status_code != 200:
                yield (chunk_id, None, f"status_code={status_code}, body={_json_dumps_compact(body)[:2000]}")
                continue

            try:
                emb = body["data"][0]["embedding"]
                if not isinstance(emb, list):
                    raise TypeError("embedding is not a list")
                yield (chunk_id, [float(x) for x in emb], None)
            except Exception as e:
                yield (chunk_id, None, f"parse_error: {e}, body={_json_dumps_compact(body)[:2000]}")


def _vector_literal(vec: Sequence[float]) -> str:
    # pgvector text input: '[1,2,3]'
    return "[" + ",".join(f"{x:.10g}" for x in vec) + "]"


def _bulk_update_embeddings(conn, items: Sequence[Tuple[str, Sequence[float]]], dims: int, only_if_null: bool = True) -> int:
    """
    Bulk UPDATE knowledge_chunks.embedding for (chunk_id, embedding) items.
    Returns number of updated rows (best-effort).
    """
    if not items:
        return 0

    # Prepare rows: (embedding_literal, chunk_id)
    rows = []
    for chunk_id, vec in items:
        if len(vec) != dims:
            raise ValueError(f"Embedding dims mismatch for {chunk_id}: got {len(vec)} expected {dims}")
        rows.append((_vector_literal(vec), chunk_id))

    where_null = "AND kc.embedding IS NULL" if only_if_null else ""
    sql = f"""
        UPDATE knowledge_chunks AS kc
        SET embedding = v.embedding::vector
        FROM (VALUES %s) AS v(embedding, id)
        WHERE kc.id = v.id::uuid
          {where_null}
    """

    with conn.cursor() as cur:
        execute_values(cur, sql, rows, template="(%s, %s)", page_size=500)
    return len(rows)


def cmd_ingest(args: argparse.Namespace) -> int:
    api_key = args.openai_api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        LOG.error("OPENAI_API_KEY must be set (or pass --openai-api-key)")
        return 2

    db_url = args.db_url or os.environ.get("DATABASE_URL")
    if not db_url:
        LOG.error("DATABASE_URL must be set (or pass --db-url)")
        return 2

    targets: List[Path] = []
    if args.batch_file:
        targets = [Path(args.batch_file)]
    elif args.run_dir:
        targets = _iter_batch_json_paths(Path(args.run_dir))
    else:
        LOG.error("Provide --batch-file or --run-dir")
        return 2

    conn = _connect_db(db_url)
    updated_total = 0
    failed_total = 0
    skipped_total = 0

    try:
        for batch_json_path in targets:
            batch_dir = batch_json_path.parent
            meta = _read_json(batch_json_path)
            batch_id = meta.get("batch_id")
            if not batch_id:
                LOG.info("%s: no batch_id (dry_run?) - skipping", batch_json_path)
                continue

            batch_obj = _openai_get_batch(args.api_base, api_key, batch_id=batch_id)
            status = batch_obj.get("status")
            out_id = batch_obj.get("output_file_id")
            err_id = batch_obj.get("error_file_id")

            LOG.info("Batch %s status=%s output=%s error=%s", batch_id, status, out_id, err_id)

            if status not in ("completed", "expired", "failed", "canceled"):
                LOG.info("Not ready to ingest (status=%s). Use `status` or rerun ingest later.", status)
                continue

            # Download output/errors if present
            if out_id:
                out_path = batch_dir / "output.jsonl"
                if not out_path.exists() or args.redownload:
                    LOG.info("Downloading output file %s -> %s", out_id, out_path)
                    _openai_download_file_content(args.api_base, api_key, out_id, out_path)
            else:
                LOG.warning("No output_file_id for batch %s (status=%s).", batch_id, status)
                continue

            if err_id:
                err_path = batch_dir / "errors.jsonl"
                if not err_path.exists() or args.redownload:
                    LOG.info("Downloading error file %s -> %s", err_id, err_path)
                    _openai_download_file_content(args.api_base, api_key, err_id, err_path)

            # Parse and update DB
            out_path = batch_dir / "output.jsonl"
            failures: List[str] = []
            updates: List[Tuple[str, Sequence[float]]] = []
            processed = 0

            for chunk_id, emb, err in _parse_output_jsonl(out_path):
                processed += 1
                if not chunk_id:
                    failures.append(f"(unknown) {err}")
                    continue
                if err or emb is None:
                    failures.append(f"{chunk_id}\t{err}")
                    continue
                updates.append((chunk_id, emb))

                # Flush updates in chunks
                if len(updates) >= args.update_chunk_size:
                    n = _bulk_update_embeddings(conn, updates, dims=args.dims, only_if_null=not args.overwrite)
                    conn.commit()
                    updated_total += n
                    updates = []

            # Flush remaining
            if updates:
                n = _bulk_update_embeddings(conn, updates, dims=args.dims, only_if_null=not args.overwrite)
                conn.commit()
                updated_total += n

            if failures:
                failed_total += len(failures)
                failed_path = batch_dir / "failed_chunk_ids.tsv"
                _write_text(failed_path, "\n".join(failures) + "\n")
                LOG.warning("Wrote %d failures to %s", len(failures), failed_path)

            # Update batch.json with ingestion info
            meta["ingested_at_utc"] = _dt.datetime.utcnow().isoformat() + "Z"
            meta["openai_batch_object_latest"] = batch_obj
            meta["ingest_stats"] = {
                "processed_output_lines": processed,
                "failed_lines": len(failures),
                "updated_rows_attempted": processed - len(failures),
            }
            _write_json(batch_json_path, meta)

            LOG.info("Ingested batch %s. processed=%d failed=%d", batch_id, processed, len(failures))

    finally:
        conn.close()

    LOG.info("DONE. updated_total=%d failed_total=%d skipped_total=%d", updated_total, failed_total, skipped_total)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """
    Convenience: submit then poll until completed then ingest.
    This requires keeping the terminal open.
    """
    # First submit
    submit_args = argparse.Namespace(**vars(args))
    submit_args.command = "submit"
    rc = cmd_submit(submit_args)
    if rc != 0:
        return rc

    # Find the newest run dir we just created
    run_root = Path(args.out_dir) / args.family_id
    run_dirs = sorted([p for p in run_root.glob("run_*") if p.is_dir()])
    if not run_dirs:
        LOG.error("Could not find run directory under %s", run_root)
        return 2
    run_dir = run_dirs[-1]
    LOG.info("Will poll and ingest run dir: %s", run_dir)

    # Poll until all batches completed/expired/failed/canceled
    api_key = args.openai_api_key or os.environ.get("OPENAI_API_KEY")
    assert api_key

    batch_json_paths = _iter_batch_json_paths(run_dir)
    pending = set(str(p) for p in batch_json_paths)

    start = time.time()
    while pending:
        done_now: List[str] = []
        for p_str in sorted(pending):
            p = Path(p_str)
            meta = _read_json(p)
            batch_id = meta.get("batch_id")
            if not batch_id:
                done_now.append(p_str)
                continue
            batch_obj = _openai_get_batch(args.api_base, api_key, batch_id=batch_id)
            status = batch_obj.get("status")
            if status in ("completed", "expired", "failed", "canceled"):
                done_now.append(p_str)
                LOG.info("Batch %s reached terminal status=%s", batch_id, status)
        for x in done_now:
            pending.discard(x)

        if pending:
            elapsed = int(time.time() - start)
            LOG.info("Waiting... pending=%d elapsed=%ss (poll every %ss)", len(pending), elapsed, args.poll_seconds)
            time.sleep(args.poll_seconds)

    # Ingest
    ingest_args = argparse.Namespace(**vars(args))
    ingest_args.command = "ingest"
    ingest_args.run_dir = str(run_dir)
    ingest_args.batch_file = None
    return cmd_ingest(ingest_args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch-embed KnowledgeChunks for an EquipmentFamily.")
    parser.add_argument("--api-base", type=str, default=DEFAULT_ENDPOINT, help="OpenAI API base (default https://api.openai.com)")
    parser.add_argument("--openai-api-key", type=str, default=None, help="OpenAI API key (or set OPENAI_API_KEY)")
    parser.add_argument("--db-url", type=str, default=os.environ.get("DATABASE_URL"), help="Postgres DSN (or set DATABASE_URL)")
    parser.add_argument("--log-level", type=str, default="INFO", help="INFO, DEBUG, ...")

    sub = parser.add_subparsers(dest="command", required=True)

    p_submit = sub.add_parser("submit", help="Create one or more OpenAI batches for all unembedded chunks in a family.")
    p_submit.add_argument("--family-id", required=True, help="EquipmentFamily.id (UUID)")
    p_submit.add_argument("--out-dir", default=str(Path(__file__).parent / "batches"), help="Where to write run folders")
    p_submit.add_argument("--model", default=DEFAULT_MODEL, help="Embedding model (default text-embedding-3-small)")
    p_submit.add_argument("--limit", type=int, default=None, help="Optional limit for number of chunks selected from DB")
    p_submit.add_argument("--max-requests-per-batch", type=int, default=DEFAULT_MAX_REQUESTS_PER_BATCH)
    p_submit.add_argument("--max-bytes-per-batch", type=int, default=DEFAULT_MAX_BYTES_PER_BATCH)
    p_submit.add_argument("--sleep-between-batches", type=float, default=0.0, help="Sleep seconds between creating batches")
    p_submit.add_argument("--dry-run", action="store_true", help="Do everything except upload/create OpenAI batches")

    p_status = sub.add_parser("status", help="Check status of a batch or all batches in a run dir.")
    p_status.add_argument("--batch-file", type=str, default=None, help="Path to a batch.json")
    p_status.add_argument("--run-dir", type=str, default=None, help="Path to a run_*/ directory")
    p_status.add_argument("--update-json", action="store_true", help="Write latest status back into batch.json")

    p_ingest = sub.add_parser("ingest", help="Download outputs and write embeddings into Postgres.")
    p_ingest.add_argument("--batch-file", type=str, default=None, help="Path to a batch.json")
    p_ingest.add_argument("--run-dir", type=str, default=None, help="Path to a run_*/ directory")
    p_ingest.add_argument("--dims", type=int, default=1536, help="Expected embedding dimensions (vector(1536))")
    p_ingest.add_argument("--update-chunk-size", type=int, default=1000, help="How many rows to update per DB flush")
    p_ingest.add_argument("--overwrite", action="store_true", help="Overwrite embeddings even if already present")
    p_ingest.add_argument("--redownload", action="store_true", help="Redownload output/error files even if already present")

    p_run = sub.add_parser("run", help="Submit + poll + ingest (keeps terminal open).")
    p_run.add_argument("--family-id", required=True, help="EquipmentFamily.id (UUID)")
    p_run.add_argument("--out-dir", default=str(Path(__file__).parent / "batches"), help="Where to write run folders")
    p_run.add_argument("--model", default=DEFAULT_MODEL, help="Embedding model (default text-embedding-3-small)")
    p_run.add_argument("--limit", type=int, default=None, help="Optional limit for number of chunks selected from DB")
    p_run.add_argument("--max-requests-per-batch", type=int, default=DEFAULT_MAX_REQUESTS_PER_BATCH)
    p_run.add_argument("--max-bytes-per-batch", type=int, default=DEFAULT_MAX_BYTES_PER_BATCH)
    p_run.add_argument("--sleep-between-batches", type=float, default=0.0, help="Sleep seconds between creating batches")
    p_run.add_argument("--poll-seconds", type=int, default=60, help="Polling interval in seconds")
    # Ingest args
    p_run.add_argument("--dims", type=int, default=1536, help="Expected embedding dimensions (vector(1536))")
    p_run.add_argument("--update-chunk-size", type=int, default=1000, help="How many rows to update per DB flush")
    p_run.add_argument("--overwrite", action="store_true", help="Overwrite embeddings even if already present")
    p_run.add_argument("--redownload", action="store_true", help="Redownload output/error files even if already present")

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    if load_dotenv is not None:
        try:
            # Load .env located in the top-level "scripts" directory (two levels up
            # from this file: scripts/embeddings/<this file> -> scripts/.env).
            env_path = Path(__file__).resolve().parent.parent / ".env"
            load_dotenv(dotenv_path=str(env_path))
        except Exception:
            # Best-effort: fall back to default behavior if explicit load fails
            try:
                load_dotenv()
            except Exception:
                pass

    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.command == "submit":
        return cmd_submit(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "ingest":
        return cmd_ingest(args)
    if args.command == "run":
        return cmd_run(args)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
