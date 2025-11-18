#!/usr/bin/env python3
"""Check what's actually in the database."""

import os
import sys
from pathlib import Path

# Add scripts directory to path and load .env (same way as main script)
sys.path.insert(0, str(Path(__file__).parent))

# Import config which loads .env file
try:
    from scripts.ifixit.config import DEFAULT_PAGE_SIZE  # This loads .env
except ImportError:
    # Fallback: try loading .env directly
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass

from scripts.db_client import DatabaseClient

try:
    db = DatabaseClient()
    print("✓ Database connection successful\n")
    
    with db.transaction() as cur:
        # Check knowledge sources
        cur.execute("SELECT COUNT(*) FROM knowledge_sources WHERE source_type = %s", ('ifixit',))
        ks_count = cur.fetchone()[0]
        print(f"Knowledge sources (ifixit): {ks_count}")
        
        # Check all knowledge sources (any source_type)
        cur.execute("SELECT COUNT(*) FROM knowledge_sources")
        ks_total = cur.fetchone()[0]
        print(f"Knowledge sources (total): {ks_total}")
        
        # Check equipment models
        cur.execute("SELECT COUNT(*) FROM equipment_models WHERE metadata->%s IS NOT NULL", ('ifixit',))
        em_count = cur.fetchone()[0]
        print(f"Equipment models (ifixit): {em_count}")
        
        # Check equipment families
        cur.execute("SELECT COUNT(*) FROM equipment_families WHERE metadata->%s IS NOT NULL", ('ifixit',))
        ef_count = cur.fetchone()[0]
        print(f"Equipment families (ifixit): {ef_count}")
        
        # Get sample records
        if ks_count > 0:
            print("\nSample knowledge sources (ifixit):")
            cur.execute("SELECT id, title, model_id, updated_at FROM knowledge_sources WHERE source_type = %s ORDER BY updated_at DESC LIMIT 5", ('ifixit',))
            for row in cur.fetchall():
                print(f"  - {row[1][:50]}... (ID: {str(row[0])[:8]}..., updated: {row[3]})")
        else:
            print("\n⚠ No knowledge sources found with source_type='ifixit'")
            if ks_total > 0:
                print(f"  But found {ks_total} total knowledge sources. Checking source_type values:")
                cur.execute("SELECT DISTINCT source_type, COUNT(*) FROM knowledge_sources GROUP BY source_type")
                for row in cur.fetchall():
                    print(f"    - source_type='{row[0]}': {row[1]} records")
        
        if em_count > 0:
            print("\nSample equipment models:")
            cur.execute("SELECT id, model_name, manufacturer FROM equipment_models WHERE metadata->%s IS NOT NULL LIMIT 5", ('ifixit',))
            for row in cur.fetchall():
                print(f"  - {row[2]} {row[1]} (ID: {str(row[0])[:8]}...)")
        
        if ef_count > 0:
            print("\nSample equipment families:")
            cur.execute("SELECT id, name FROM equipment_families WHERE metadata->%s IS NOT NULL LIMIT 5", ('ifixit',))
            for row in cur.fetchall():
                print(f"  - {row[1]} (ID: {str(row[0])[:8]}...)")
        
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
