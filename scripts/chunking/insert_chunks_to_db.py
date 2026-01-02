#!/usr/bin/env python3
"""
Database Insertion Script for knowledge_chunks table

This script reads the JSON output from pdf_text_chunker.py and inserts it
into your PostgreSQL knowledge_chunks table.

Prerequisites:
- PostgreSQL with pgvector extension enabled
- knowledge_sources table with existing records
- Environment variables: DATABASE_URL (or use --connection-string)

Usage:
    python insert_chunks_to_db.py \
        --chunks-file db_schema_chunks.json \
        --connection-string "postgresql://user:password@localhost/dbname" \
        --source-id "550e8400-e29b-41d4-a716-446655440000" \
        --batch-size 100

With embeddings:
    python insert_chunks_to_db.py \
        --chunks-file chunks_with_embeddings.json \
        --connection-string "postgresql://..." \
        --source-id "550e8400-e29b-41d4-a716-446655440000"
"""

import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import os


class KnowledgeChunksInserter:
    """Insert chunks into knowledge_chunks table"""

    def __init__(self, connection_string: Optional[str] = None):
        """
        Initialize database connection

        Args:
            connection_string: PostgreSQL connection string
                             or None to use DATABASE_URL env var
        """
        self.connection_string = (
            connection_string or os.getenv("DATABASE_URL")
        )

        if not self.connection_string:
            raise ValueError(
                "DATABASE_URL environment variable or --connection-string required"
            )

        # Import psycopg2 (required for database operations)
        try:
            import psycopg2
            from psycopg2.extras import execute_batch
            self.psycopg2 = psycopg2
            self.execute_batch = execute_batch
        except ImportError:
            raise ImportError(
                "psycopg2 required. Install with: pip install psycopg2-binary"
            )

    def load_chunks(self, json_path: str) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Load chunks from JSON file"""
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data.get("chunks", []), data.get("metadata", {})

    def prepare_insert_records(
        self,
        chunks: List[Dict[str, Any]],
        source_id: Optional[str] = None,
    ) -> List[tuple]:
        """
        Prepare chunk records for database insertion

        Returns:
            List of tuples matching INSERT statement order
        """
        records = []

        for chunk in chunks:
            # Use source_id from parameter or from chunk data
            chunk_source_id = source_id or chunk.get("source_id")

            if not chunk_source_id:
                print(f"⚠️  Warning: Chunk {chunk['chunk_index']} has no source_id, skipping")
                continue

            # Prepare record (matching column order in INSERT)
            record = (
                chunk_source_id,  # source_id
                chunk["chunk_index"],  # chunk_index
                chunk["content"],  # content
                chunk.get("heading"),  # heading
                chunk.get("embedding"),  # embedding (VECTOR, can be None)
                chunk["token_count"],  # token_count
                json.dumps(chunk["metadata"]),  # metadata (JSONB)
            )

            records.append(record)

        return records

    def insert_chunks(
        self,
        chunks: List[Dict[str, Any]],
        source_id: Optional[str] = None,
        batch_size: int = 100,
        dry_run: bool = False,
    ) -> int:
        """
        Insert chunks into database

        Args:
            chunks: List of chunk dictionaries
            source_id: UUID of knowledge source
            batch_size: Number of records per batch
            dry_run: If True, don't actually insert (just show SQL)

        Returns:
            Number of inserted records
        """
        # Prepare records
        records = self.prepare_insert_records(chunks, source_id)

        if not records:
            print("❌ No valid records to insert")
            return 0

        print(f"Prepared {len(records)} records for insertion")

        if dry_run:
            print("\n[DRY RUN] First 3 records:")
            for i, record in enumerate(records[:3]):
                print(f"  {i+1}: chunk_index={record[1]}, heading={record[3]}")
            print(f"\nTotal: {len(records)} records would be inserted")
            return len(records)

        # Connect to database
        conn = self.psycopg2.connect(self.connection_string)
        cur = conn.cursor()

        try:
            insert_sql = """
            INSERT INTO public.knowledge_chunks
            (source_id, chunk_index, content, heading, embedding, token_count, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """

            # Insert in batches
            inserted = 0
            for i in range(0, len(records), batch_size):
                batch = records[i : i + batch_size]
                self.execute_batch(cur, insert_sql, batch)
                inserted += len(batch)

                if (i + batch_size) % (batch_size * 10) == 0:
                    print(f"  Inserted {inserted}/{len(records)}...")

            conn.commit()
            print(f"✓ Successfully inserted {inserted} chunks")

            return inserted

        except Exception as e:
            conn.rollback()
            print(f"❌ Error during insertion: {e}")
            raise

        finally:
            cur.close()
            conn.close()

    def verify_insertion(self, source_id: str, expected_count: int) -> bool:
        """
        Verify that chunks were inserted correctly

        Args:
            source_id: UUID of knowledge source
            expected_count: Expected number of chunks

        Returns:
            True if verified, False otherwise
        """
        conn = self.psycopg2.connect(self.connection_string)
        cur = conn.cursor()

        try:
            cur.execute(
                "SELECT COUNT(*) FROM public.knowledge_chunks WHERE source_id = %s",
                (source_id,),
            )
            actual_count = cur.fetchone()[0]

            if actual_count == expected_count:
                print(f"✓ Verified: {actual_count} chunks inserted for source {source_id}")
                return True
            else:
                print(
                    f"⚠️  Verification failed: expected {expected_count}, found {actual_count}"
                )
                return False

        finally:
            cur.close()
            conn.close()

    def get_source_stats(self, source_id: str) -> Dict[str, Any]:
        """Get statistics for a knowledge source"""
        conn = self.psycopg2.connect(self.connection_string)
        cur = conn.cursor()

        try:
            cur.execute(
                """
                SELECT
                    COUNT(*) as total_chunks,
                    SUM(token_count) as total_tokens,
                    AVG(token_count) as avg_tokens,
                    COUNT(CASE WHEN embedding IS NOT NULL THEN 1 END) as with_embeddings,
                    COUNT(CASE WHEN (metadata->>'is_procedure')::boolean THEN 1 END) as procedures,
                    COUNT(CASE WHEN (metadata->>'is_table')::boolean THEN 1 END) as tables
                FROM public.knowledge_chunks
                WHERE source_id = %s
                """,
                (source_id,),
            )

            row = cur.fetchone()
            if row:
                return {
                    "total_chunks": row[0],
                    "total_tokens": row[1],
                    "avg_tokens": float(row[2]) if row[2] else 0,
                    "with_embeddings": row[3],
                    "procedures": row[4],
                    "tables": row[5],
                }

            return {}

        finally:
            cur.close()
            conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Insert PDF chunks into knowledge_chunks table"
    )
    parser.add_argument(
        "-f",
        "--chunks-file",
        required=True,
        help="JSON file with chunks (output from pdf_text_chunker.py)",
    )
    parser.add_argument(
        "-c",
        "--connection-string",
        help="PostgreSQL connection string (or use DATABASE_URL env var)",
    )
    parser.add_argument(
        "-s",
        "--source-id",
        required=True,
        help="UUID of the knowledge source",
    )
    parser.add_argument(
        "-b",
        "--batch-size",
        type=int,
        default=100,
        help="Records per batch (default: 100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually insert, just show what would happen",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify insertion after completing",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show statistics after insertion",
    )

    args = parser.parse_args()

    # Validate input file
    chunks_file = Path(args.chunks_file)
    if not chunks_file.exists():
        print(f"Error: Chunks file not found: {args.chunks_file}")
        return 1

    print("=" * 80)
    print("DATABASE INSERTION: knowledge_chunks")
    print("=" * 80)

    try:
        # Initialize inserter
        inserter = KnowledgeChunksInserter(args.connection_string)

        # Load chunks
        print(f"\nLoading chunks from {args.chunks_file}...")
        chunks, metadata = inserter.load_chunks(args.chunks_file)
        print(f"  Loaded {len(chunks)} chunks")
        print(f"  Source ID: {args.source_id}")

        # Insert
        print(f"\nInserting into database (batch size: {args.batch_size})...")
        if args.dry_run:
            print("  [DRY RUN MODE]")

        inserted_count = inserter.insert_chunks(
            chunks,
            source_id=args.source_id,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )

        if args.dry_run:
            print("\n[DRY RUN] No actual insertion performed")
            return 0

        # Verify
        if args.verify:
            print("\nVerifying insertion...")
            verified = inserter.verify_insertion(args.source_id, len(chunks))
            if not verified:
                return 1

        # Stats
        if args.stats:
            print("\nFetching statistics...")
            stats = inserter.get_source_stats(args.source_id)
            if stats:
                print(f"  Total chunks: {stats['total_chunks']}")
                print(f"  Total tokens: {stats['total_tokens']}")
                print(f"  Avg tokens/chunk: {stats['avg_tokens']:.1f}")
                print(f"  With embeddings: {stats['with_embeddings']}")
                print(f"  Procedure chunks: {stats['procedures']}")
                print(f"  Table chunks: {stats['tables']}")

        print("\n" + "=" * 80)
        print("✅ Complete!")
        print("=" * 80)

        return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
