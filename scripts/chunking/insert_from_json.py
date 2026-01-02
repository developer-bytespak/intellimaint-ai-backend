#!/usr/bin/env python3
"""
Insert Chunks from JSON
=======================

Reads chunk data from a JSON file and inserts them into the database.

Usage:
    python insert_from_json.py sample_chunks.json
    python insert_from_json.py chunk_data.json
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import Json


def main():
    if len(sys.argv) < 2:
        print("Usage: python insert_from_json.py <json_file>")
        print("Example: python insert_from_json.py sample_chunks.json")
        return 1
    
    json_file = sys.argv[1]
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        print("❌ DATABASE_URL environment variable not set")
        return 1
    
    # Check if file exists
    if not Path(json_file).exists():
        print(f"❌ File not found: {json_file}")
        return 1
    
    try:
        # Read JSON file
        print(f"\n📖 Reading JSON: {json_file}")
        with open(json_file) as f:
            data = json.load(f)
        
        source_id = data.get("source_id")
        source_title = data.get("source_title")
        chunks = data.get("chunks", [])
        
        print(f"   Source: {source_title}")
        print(f"   Source ID: {source_id}")
        print(f"   Chunks to insert: {len(chunks)}")
        
        # Connect to database
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        # Check if source exists
        cursor.execute(
            "SELECT id FROM knowledge_sources WHERE id = %s",
            (source_id,)
        )
        if not cursor.fetchone():
            print(f"\n⚠️  Source not found in database: {source_id}")
            print("   Creating entry...")
            cursor.execute(
                "INSERT INTO knowledge_sources (id, title) VALUES (%s, %s)",
                (source_id, source_title)
            )
            conn.commit()
            print("   ✓ Source created")
        
        # Check if chunks already exist
        cursor.execute(
            "SELECT COUNT(*) FROM knowledge_chunks WHERE source_id = %s",
            (source_id,)
        )
        existing_count = cursor.fetchone()[0]
        
        if existing_count > 0:
            print(f"\n⚠️  This source already has {existing_count} chunks")
            confirm = input("Delete and reprocess? (yes/no): ").strip().lower()
            if confirm == "yes":
                cursor.execute("DELETE FROM knowledge_chunks WHERE source_id = %s", (source_id,))
                conn.commit()
                print(f"   Deleted {existing_count} existing chunks")
            else:
                print("Cancelled")
                return 0
        
        # Insert chunks one by one
        print(f"\n💾 Inserting chunks from JSON:")
        
        inserted_count = 0
        for chunk in chunks:
            try:
                cursor.execute(
                    """
                    INSERT INTO knowledge_chunks 
                    (id, source_id, chunk_index, content, heading, embedding, 
                     token_count, metadata, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        chunk.get("id"),
                        chunk.get("source_id"),
                        chunk.get("chunk_index"),
                        chunk.get("content"),
                        chunk.get("heading"),
                        chunk.get("embedding"),  # Usually None
                        chunk.get("token_count"),
                        Json(chunk.get("metadata", {})),
                        chunk.get("created_at") or datetime.utcnow().isoformat()
                    )
                )
                
                # Print progress
                heading = chunk.get("heading") or "(no heading)"
                tokens = chunk.get("token_count", 0)
                print(f"   [{inserted_count + 1}/{len(chunks)}] {heading} ({tokens} tokens)")
                inserted_count += 1
            
            except Exception as e:
                print(f"   ✗ Error inserting chunk {inserted_count}: {e}")
                conn.rollback()
                cursor.close()
                conn.close()
                return 1
        
        # Commit all inserts
        conn.commit()
        
        # Verify
        cursor.execute(
            "SELECT COUNT(*) FROM knowledge_chunks WHERE source_id = %s",
            (source_id,)
        )
        final_count = cursor.fetchone()[0]
        
        print(f"\n✅ Success!")
        print(f"   Inserted {final_count} chunks into database")
        
        # Show sample
        cursor.execute(
            """
            SELECT chunk_index, heading, length(content) as content_len, token_count
            FROM knowledge_chunks
            WHERE source_id = %s
            ORDER BY chunk_index
            LIMIT 3
            """,
            (source_id,)
        )
        
        samples = cursor.fetchall()
        if samples:
            print(f"\n📊 Sample chunks:")
            for chunk_index, heading, content_len, token_count in samples:
                heading_display = heading or "(no heading)"
                print(f"   Chunk {chunk_index}: {heading_display} ({content_len} chars, {token_count} tokens)")
        
        cursor.close()
        conn.close()
        return 0
    
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
