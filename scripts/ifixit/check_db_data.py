#!/usr/bin/env python3
"""Check what iFixit data is in the database."""

import logging
import os
import sys
from pathlib import Path

# Load environment variables from .env file
# Try multiple locations (project root and gateway directory)
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent.parent
env_paths = [
    project_root / '.env',
    project_root / 'gateway' / '.env',
]
for env_path in env_paths:
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
        break
else:
    # If no .env file found, try loading from current directory
    load_dotenv(override=False)

from scripts.db_client import DatabaseClient, DatabaseConnectionError

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def check_database_content(db_client: DatabaseClient):
    """Check what iFixit data exists in the database."""
    db_client._ensure_connection()
    
    logger.info("=" * 80)
    logger.info("Checking iFixit Skills data in database...")
    logger.info("=" * 80)
    
    # ========================================================================
    # KNOWLEDGE_SOURCES TABLE
    # ========================================================================
    logger.info("\n" + "=" * 80)
    logger.info("TABLE: knowledge_sources")
    logger.info("=" * 80)
    
    # Total iFixit guides
    db_client._cursor.execute(
        "SELECT COUNT(*) FROM knowledge_sources WHERE source_type = 'ifixit'"
    )
    total_guides = db_client._cursor.fetchone()[0]
    logger.info(f"\n  Total iFixit guides: {total_guides}")
    
    # Guides with skills in metadata
    db_client._cursor.execute("""
        SELECT COUNT(*) 
        FROM knowledge_sources 
        WHERE source_type = 'ifixit' 
        AND metadata::text LIKE '%Skills%'
    """)
    skills_guides = db_client._cursor.fetchone()[0]
    logger.info(f"  Skills guides found: {skills_guides}")
    
    # Sample skills guides
    db_client._cursor.execute("""
        SELECT id, title, model_id, 
               metadata->'ifixit'->>'device_path' as device_path,
               metadata->'ifixit'->>'guide_id' as guide_id
        FROM knowledge_sources 
        WHERE source_type = 'ifixit' 
        AND metadata::text LIKE '%Skills%'
        LIMIT 5
    """)
    sample_skills_guides = db_client._cursor.fetchall()
    if sample_skills_guides:
        logger.info(f"\n  Sample Skills guides from knowledge_sources (showing {len(sample_skills_guides)}):")
        for guide in sample_skills_guides:
            title_preview = (guide[1][:50] + "...") if guide[1] and len(guide[1]) > 50 else (guide[1] or "N/A")
            logger.info(f"    - ID: {guide[0]}")
            logger.info(f"      Title: {title_preview}")
            logger.info(f"      Model ID: {guide[2]}")
            logger.info(f"      Device Path: {guide[3]}")
            logger.info(f"      Guide ID: {guide[4]}")
            logger.info("")
    else:
        logger.info("\n  ⚠️  No Skills guides found in knowledge_sources table")
    
    # ========================================================================
    # EQUIPMENT_MODELS TABLE
    # ========================================================================
    logger.info("\n" + "=" * 80)
    logger.info("TABLE: equipment_models")
    logger.info("=" * 80)
    
    # Total iFixit devices
    db_client._cursor.execute("""
        SELECT COUNT(*) 
        FROM equipment_models 
        WHERE metadata::text LIKE '%ifixit%'
    """)
    total_devices = db_client._cursor.fetchone()[0]
    logger.info(f"\n  Total iFixit devices: {total_devices}")
    
    # Skills devices
    db_client._cursor.execute("""
        SELECT COUNT(*) 
        FROM equipment_models 
        WHERE metadata::text LIKE '%ifixit%'
        AND (metadata->'ifixit'->>'path' LIKE 'Skills%' 
             OR model_name LIKE '%Skills%')
    """)
    skills_devices = db_client._cursor.fetchone()[0]
    logger.info(f"  Skills devices found: {skills_devices}")
    
    # Sample skills devices
    db_client._cursor.execute("""
        SELECT id, model_name, manufacturer,
               metadata->'ifixit'->>'path' as device_path
        FROM equipment_models 
        WHERE metadata::text LIKE '%ifixit%'
        AND (metadata->'ifixit'->>'path' LIKE 'Skills%' 
             OR model_name LIKE '%Skills%')
        LIMIT 5
    """)
    sample_skills_devices = db_client._cursor.fetchall()
    if sample_skills_devices:
        logger.info(f"\n  Sample Skills devices from equipment_models (showing {len(sample_skills_devices)}):")
        for device in sample_skills_devices:
            logger.info(f"    - ID: {device[0]}")
            logger.info(f"      Name: {device[1]}")
            logger.info(f"      Manufacturer: {device[2]}")
            logger.info(f"      Device Path: {device[3]}")
            logger.info("")
    else:
        logger.info("\n  ⚠️  No Skills devices found in equipment_models table")
    
    # ========================================================================
    # EQUIPMENT_FAMILIES TABLE
    # ========================================================================
    logger.info("\n" + "=" * 80)
    logger.info("TABLE: equipment_families")
    logger.info("=" * 80)
    
    db_client._cursor.execute("""
        SELECT COUNT(*) 
        FROM equipment_families 
        WHERE metadata::text LIKE '%ifixit%'
    """)
    total_families = db_client._cursor.fetchone()[0]
    logger.info(f"\n  Total iFixit families: {total_families}")
    
    # Skills family
    db_client._cursor.execute("""
        SELECT id, name 
        FROM equipment_families 
        WHERE metadata::text LIKE '%ifixit%'
        AND (name = 'Skills' OR metadata->'ifixit'->>'path' = 'Skills')
    """)
    skills_family = db_client._cursor.fetchone()
    if skills_family:
        logger.info(f"\n  Skills family found in equipment_families:")
        logger.info(f"    - ID: {skills_family[0]}")
        logger.info(f"    - Name: {skills_family[1]}")
    else:
        logger.info("\n  ⚠️  Skills family not found in equipment_families table")
    
    # ========================================================================
    # KNOWLEDGE_CHUNKS TABLE
    # ========================================================================
    logger.info("\n" + "=" * 80)
    logger.info("TABLE: knowledge_chunks")
    logger.info("=" * 80)
    
    db_client._cursor.execute("""
        SELECT COUNT(*) 
        FROM knowledge_chunks kc
        JOIN knowledge_sources ks ON kc.source_id = ks.id
        WHERE ks.source_type = 'ifixit'
    """)
    total_chunks = db_client._cursor.fetchone()[0]
    logger.info(f"\n  Total chunks from iFixit sources: {total_chunks}")
    
    if total_chunks == 0:
        logger.info("  ⚠️  No chunks found - chunks are created separately by a chunking process")
    
    # ========================================================================
    # CROSS-TABLE RELATIONSHIPS
    # ========================================================================
    logger.info("\n" + "=" * 80)
    logger.info("CROSS-TABLE: Guides linked to Skills devices")
    logger.info("=" * 80)
    
    db_client._cursor.execute("""
        SELECT COUNT(DISTINCT ks.id)
        FROM knowledge_sources ks
        JOIN equipment_models em ON ks.model_id = em.id
        WHERE ks.source_type = 'ifixit'
        AND (em.metadata->'ifixit'->>'path' LIKE 'Skills%' 
             OR em.model_name LIKE '%Skills%')
    """)
    linked_skills_guides = db_client._cursor.fetchone()[0]
    logger.info(f"\n  Guides from knowledge_sources linked to Skills devices in equipment_models: {linked_skills_guides}")
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("SUMMARY:")
    logger.info("=" * 80)
    logger.info(f"  Knowledge Sources (Guides): {total_guides} total, {skills_guides} with 'Skills' in metadata")
    logger.info(f"  Equipment Models (Devices): {total_devices} total, {skills_devices} skills devices")
    logger.info(f"  Equipment Families (Categories): {total_families} total")
    logger.info(f"  Knowledge Chunks: {total_chunks} total")
    logger.info(f"  Guides linked to skills devices: {linked_skills_guides}")
    
    if skills_guides == 0 and skills_devices > 0:
        logger.info("\n⚠️  ISSUE DETECTED:")
        logger.info("   Skills devices exist but no skills guides in knowledge_sources!")
        logger.info("   This suggests the guides were not written to the database.")
    elif skills_guides > 0:
        logger.info("\n✓ Skills guides found in knowledge_sources")
    
    logger.info("=" * 80)


def main():
    """Main entry point."""
    try:
        db_client = DatabaseClient()
        logger.info("✓ Database connection established successfully")
    except DatabaseConnectionError as exc:
        logger.error(f"✗ Database connection failed: {exc}")
        logger.error("Please ensure DATABASE_URL is set in your environment or .env file")
        sys.exit(1)
    
    try:
        check_database_content(db_client)
    except Exception as exc:
        logger.error(f"Error checking database: {exc}", exc_info=True)
        sys.exit(1)
    finally:
        try:
            db_client.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()

