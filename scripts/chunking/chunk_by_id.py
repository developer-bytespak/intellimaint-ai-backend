#!/usr/bin/env python3
"""
Simple Chunk Processor
======================

Takes a knowledge_source ID and chunks its raw_content one by one into the database.
Also saves chunks to a JSON file.

Usage:
    python chunk_by_id.py "550e8400-e29b-41d4-a716-446655440000"
    python chunk_by_id.py <source_id>
"""

import os
import sys
import uuid
import json
from datetime import datetime

import psycopg2
from psycopg2.extras import Json

# Add chunking module to path
sys.path.insert(0, os.path.dirname(__file__))
from pdf_universal_chunker import UniversalChunkingPipeline


def main():
    if len(sys.argv) < 2:
        print("Usage: python chunk_by_id.py <source_id>")
        print("Example: python chunk_by_id.py 550e8400-e29b-41d4-a716-446655440000")
        return 1
    
    source_id = sys.argv[1]
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        print("❌ DATABASE_URL environment variable not set")
        return 1
    
    try:
        # Connect to database
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        # Get the source
        print(f"\n📄 Fetching source: {source_id}")
        cursor.execute(
            "SELECT id, title, raw_content FROM knowledge_sources WHERE id = %s",
            (source_id,)
        )
        result = cursor.fetchone()
        
        if not result:
            print(f"❌ Source not found: {source_id}")
            return 1
        
        db_id, title, raw_content = result
        print(f"   Title: {title}")
        print(f"   Content length: {len(raw_content)} chars")
        
        # Check if already has chunks
        cursor.execute(
            "SELECT COUNT(*) FROM knowledge_chunks WHERE source_id = %s",
            (source_id,)
        )
        existing_count = cursor.fetchone()[0]
        
        if existing_count > 0:
            print(f"⚠️  This source already has {existing_count} chunks")
            confirm = input("Delete and reprocess? (yes/no): ").strip().lower()
            if confirm == "yes":
                cursor.execute("DELETE FROM knowledge_chunks WHERE source_id = %s", (source_id,))
                conn.commit()
                print(f"   Deleted {existing_count} existing chunks")
            else:
                print("Cancelled")
                return 0
        
        # Run chunking pipeline
        print(f"\n🔄 Chunking content...")
        pipeline = UniversalChunkingPipeline()
        chunks = pipeline.process(raw_content, source_id=source_id)
        
        if not chunks:
            print("❌ No chunks created")
            return 1
        
        print(f"   ✓ Created {len(chunks)} chunks")
        
        # Insert chunks one by one
        print(f"\n💾 Inserting chunks into database:")
        
        chunks_data = []
        for i, chunk in enumerate(chunks):
            chunk_id = str(uuid.uuid4())
            chunk_data = chunk.to_dict(source_id=source_id)
            
            cursor.execute(
                """
                INSERT INTO knowledge_chunks 
                (id, source_id, chunk_index, content, heading, embedding, 
                 token_count, metadata, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    chunk_id,
                    source_id,
                    chunk_data["chunk_index"],
                    chunk_data["content"],
                    chunk_data.get("heading"),
                    None,  # embedding
                    chunk_data.get("token_count"),
                    Json(chunk_data.get("metadata", {})),
                    datetime.utcnow()
                )
            )
            
            # Prepare data for JSON
            chunk_json = {
                "id": chunk_id,
                "source_id": source_id,
                "chunk_index": chunk_data["chunk_index"],
                "heading": chunk_data.get("heading"),
                "content": chunk_data["content"],
                "token_count": chunk_data.get("token_count"),
                "metadata": chunk_data.get("metadata", {}),
                "embedding": None,
                "created_at": datetime.utcnow().isoformat() + "Z"
            }
            chunks_data.append(chunk_json)
            
            # Print progress
            heading = chunk_data.get("heading") or "(no heading)"
            tokens = chunk_data.get("token_count", 0)
            print(f"   [{i+1}/{len(chunks)}] {heading} ({tokens} tokens)")
        
        # Commit all inserts
        conn.commit()
        
        # Verify
        cursor.execute(
            "SELECT COUNT(*) FROM knowledge_chunks WHERE source_id = %s",
            (source_id,)
        )
        inserted_count = cursor.fetchone()[0]
        
        print(f"\n✅ Success!")
        print(f"   Inserted {inserted_count} chunks into database")
        
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
        
        # Save to JSON file
        json_filename = f"chunks_{source_id[:8]}.json"
        json_data = {
            "source_id": source_id,
            "source_title": title,
            "chunks": chunks_data,
            "summary": {
                "total_chunks": len(chunks_data),
                "total_tokens": sum(c.get("token_count", 0) for c in chunks_data),
                "processing_timestamp": datetime.utcnow().isoformat() + "Z"
            }
        }
        
        with open(json_filename, 'w') as f:
            json.dump(json_data, f, indent=2)
        
        print(f"\n📁 JSON saved: {json_filename}")
        
        cursor.close()
        conn.close()
        return 0
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
