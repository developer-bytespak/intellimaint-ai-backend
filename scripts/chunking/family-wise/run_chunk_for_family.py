#!/usr/bin/env python3
"""
One-off script to run chunking API for all knowledge_sources of a given equipment family.

Set FAMILY_ID constant in this file, or pass --family.
By default the script runs in dry-run mode (no DB writes).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import json
import logging
from typing import List
import uuid
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor, register_uuid

try:
    import requests
except Exception:  # pragma: no cover - runtime dependency
    requests = None

# Set this if you want to hardcode a family id here; otherwise pass --family on CLI
FAMILY_ID = "PUT_FAMILY_ID_HERE"

API_URL = os.environ.get("API_URL", "http://localhost:8000")

# Load environment variables from scripts/.env
loaded_dotenv = False
try:
    from dotenv import load_dotenv
    dotenv_path = Path(__file__).resolve().parents[2] / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path)
    else:
        load_dotenv()
    loaded_dotenv = True
except Exception:
    loaded_dotenv = False

# If python-dotenv isn't available, try a minimal manual .env loader
if not loaded_dotenv:
    try:
        dotenv_path = Path(__file__).resolve().parents[2] / ".env"
        if dotenv_path.exists():
            with open(dotenv_path, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k:
                        os.environ.setdefault(k, v)
    except Exception:
        # ignore failures; script will check for DATABASE_URL later
        pass

DEFAULT_DB_URL = os.environ.get("DATABASE_URL")

logger = logging.getLogger("chunk_runner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def get_model_ids_for_family(conn_dsn: str, family_id: str) -> List[str]:
    conn = psycopg2.connect(conn_dsn, sslmode="require")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id FROM equipment_models WHERE family_id = %s", (family_id,))
            rows = cur.fetchall()
            return [r["id"] for r in rows]
    finally:
        conn.close()


def get_source_ids_for_models(conn_dsn: str, model_ids: List[str]) -> List[str]:
    if not model_ids:
        return []
    # Convert model id strings to uuid.UUID objects so psycopg2 sends a uuid[] parameter
    try:
        model_uuids = [uuid.UUID(m) for m in model_ids]
    except Exception:
        # if conversion fails, fall back to using raw strings (will likely error on DB)
        model_uuids = model_ids

    conn = psycopg2.connect(conn_dsn, sslmode="require")
    # ensure psycopg2 knows how to adapt uuid.UUID and uuid[] parameters
    try:
        register_uuid(conn)
    except Exception:
        # ignore if registration fails; psycopg2 may already support uuid
        pass
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id FROM knowledge_sources WHERE model_id = ANY(%s)", (model_uuids,))
            rows = cur.fetchall()
            return [str(r["id"]) for r in rows]
    finally:
        conn.close()


def call_chunk_api(api_base: str, source_id: str, dry_run: bool = True, overwrite: bool = False) -> dict:
    if requests is None:
        raise RuntimeError("requests library is required. install with `pip install requests`")
    url = api_base.rstrip("/") + "/api/v1/chunk/process"
    payload = {"source_id": source_id, "dry_run": dry_run, "overwrite": overwrite}

    max_attempts = 3
    backoff = 1.0
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.post(url, json=payload, timeout=120)
            if resp.status_code in (200, 201):
                return resp.json()
            if resp.status_code == 202:
                return {"accepted": True, "status_code": 202}
            # treat other 4xx as permanent
            if 400 <= resp.status_code < 500:
                return {"error": True, "status_code": resp.status_code, "text": resp.text}
            # otherwise retry
            logger.warning("HTTP %s for %s, attempt %d", resp.status_code, source_id, attempt)
        except Exception as e:
            logger.warning("Request failed for %s attempt %d: %s", source_id, attempt, e)
        time.sleep(backoff)
        backoff *= 2.0
    return {"error": True, "reason": "max_attempts_exceeded"}


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run chunking API for a family of equipment models")
    parser.add_argument("--family", type=str, help="equipment_family id (overrides script constant)")
    parser.add_argument("--source-id", type=str, help="Process a single knowledge_source id (skips family lookup)")
    parser.add_argument("--db-url", type=str, default=DEFAULT_DB_URL, help="Postgres DSN (or set DATABASE_URL)")
    parser.add_argument("--api-url", type=str, default=API_URL, help="Base API URL")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", help="Run dry-run (no DB writes)")
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false", help="Perform real run (writes to DB via API)")
    parser.add_argument("--overwrite", action="store_true", help="Pass overwrite=true to chunking API to replace existing chunks")
    parser.set_defaults(dry_run=True)

    args = parser.parse_args(argv)

    family_id = args.family or os.environ.get("FAMILY_ID") or FAMILY_ID

    # If a single source id is provided, skip family/model lookup
    if args.source_id:
        source_ids = [args.source_id]
        logger.info("Using single source_id override: %s", args.source_id)
    else:
        if not family_id or family_id == "PUT_FAMILY_ID_HERE":
            logger.error("FAMILY_ID must be provided via --family, env FAMILY_ID, or by editing the script constant.")
            return 2

        if not args.db_url:
            logger.error("DATABASE_URL must be set in the environment or passed with --db-url")
            return 2

        logger.info("Running chunking for family=%s dry_run=%s overwrite=%s", family_id, args.dry_run, args.overwrite)

        # Lookup models -> sources
        model_ids = get_model_ids_for_family(args.db_url, family_id)
        logger.info("Found %d models for family %s", len(model_ids), family_id)

        source_ids = get_source_ids_for_models(args.db_url, model_ids)
        logger.info("Found %d knowledge sources for family %s", len(source_ids), family_id)

    failed = []
    success = 0

    for sid in source_ids:
        logger.info("Processing source_id=%s", sid)
        res = call_chunk_api(args.api_url, sid, dry_run=args.dry_run, overwrite=args.overwrite)
        if res is None:
            logger.error("No response for %s", sid)
            failed.append(sid)
            continue
        if res.get("error"):
            logger.error("API error for %s: %s", sid, res)
            failed.append(sid)
            continue
        # dry-run returns chunk list, else 202
        if args.dry_run:
            num = res.get("num_chunks") or (len(res.get("chunks") or []))
            logger.info("Dry-run result for %s - num_chunks=%s", sid, num)
        else:
            if res.get("accepted") or res.get("status_code") == 202:
                logger.info("Accepted background job for %s", sid)
            else:
                logger.info("API response for %s: %s", sid, res)
        success += 1

    # write failures
    if failed:
        out_path = os.path.join(os.path.dirname(__file__), "failed_sources.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            for s in failed:
                f.write(s + "\n")
        logger.info("Wrote %d failed source ids to %s", len(failed), out_path)

    logger.info("Done: success=%d failed=%d", success, len(failed))
    return 0 if not failed else 3


if __name__ == "__main__":
    raise SystemExit(main())
