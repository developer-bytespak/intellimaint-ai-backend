#!/usr/bin/env python3
"""Load guides from JSON file and write to database."""

import json
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


def load_json_file(json_path: Path) -> dict:
    """Load JSON data from file."""
    logger.info(f"Loading JSON file: {json_path}")
    with json_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_guides_to_db(db_client: DatabaseClient, guides_data: dict):
    """Write guides from JSON data to database."""
    guides = guides_data.get("guides", [])
    families = guides_data.get("families", [])
    devices = guides_data.get("devices", [])
    applicable_devices_updates = guides_data.get("applicable_devices_updates", [])
    
    logger.info(f"Found {len(guides)} guides, {len(families)} families, {len(devices)} devices")
    
    db_client._ensure_connection()
    
    # Write families first
    if families:
        logger.info(f"Writing {len(families)} families to database...")
        for family_data in families:
            try:
                db_client.upsert_equipment_family(
                    family_id=family_data["family_id"],
                    name=family_data["name"],
                    description=family_data.get("description"),
                    metadata=family_data.get("metadata", {}),
                )
            except Exception as exc:
                logger.warning(f"Failed to write family {family_data['family_id'][:8]}: {exc}")
        
        try:
            db_client._connection.commit()
            logger.info(f"✓ Wrote {len(families)} families to database")
        except Exception as exc:
            logger.warning(f"Error committing families: {exc}")
    
    # Write devices
    if devices:
        logger.info(f"Writing {len(devices)} devices to database...")
        device_count = 0
        for device_data in devices:
            try:
                db_client.upsert_equipment_model(
                    model_id=device_data["model_id"],
                    family_id=device_data["family_id"],
                    manufacturer=device_data.get("manufacturer"),
                    model_name=device_data.get("model_name"),
                    model_number=device_data.get("model_number"),
                    description=device_data.get("description"),
                    metadata=device_data.get("metadata", {}),
                    image_urls=device_data.get("image_urls"),
                )
                device_count += 1
                if device_count % 50 == 0:
                    db_client._connection.commit()
                    logger.debug(f"Wrote {device_count} devices")
            except Exception as exc:
                logger.warning(f"Failed to write device {device_data['model_id'][:8]}: {exc}")
        
        try:
            db_client._connection.commit()
            logger.info(f"✓ Wrote {device_count} devices to database")
        except Exception as exc:
            logger.warning(f"Error committing devices: {exc}")
    
    # Write guides
    if guides:
        logger.info(f"Writing {len(guides)} guides to database in batches...")
        BATCH_SIZE = 100
        total_written = 0
        
        for batch_start in range(0, len(guides), BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, len(guides))
            batch = guides[batch_start:batch_end]
            
            try:
                for guide_data in batch:
                    db_client.upsert_knowledge_source(
                        source_id=guide_data["source_id"],
                        title=guide_data["title"],
                        raw_content=guide_data["raw_content"],
                        model_id=guide_data.get("model_id"),
                        word_count=guide_data.get("word_count"),
                        metadata=guide_data.get("metadata", {}),
                    )
                
                # Commit batch
                db_client._connection.commit()
                total_written += len(batch)
                
                logger.info(f"💾 Wrote batch {batch_start + 1}-{batch_end} to database ({total_written}/{len(guides)} total, {total_written / len(guides) * 100:.1f}%)")
                
            except Exception as exc:
                logger.error(f"Error writing batch {batch_start + 1}-{batch_end}: {exc}", exc_info=True)
                try:
                    db_client._connection.rollback()
                except Exception:
                    pass
        
        # Update applicable devices for existing guides
        if applicable_devices_updates:
            logger.info(f"Updating applicable devices for {len(applicable_devices_updates)} guides...")
            update_count = 0
            for update in applicable_devices_updates:
                try:
                    update_metadata = {
                        "ifixit": {
                            "applicable_devices": [update["applicable_device_info"]]
                        }
                    }
                    db_client.upsert_knowledge_source(
                        source_id=update["guide_uuid"],
                        title="",  # Preserve existing
                        raw_content="",  # Preserve existing
                        model_id=None,  # Don't change primary
                        word_count=None,
                        metadata=update_metadata,
                    )
                    update_count += 1
                    if update_count % 50 == 0:
                        db_client._connection.commit()
                        logger.debug(f"Updated {update_count} applicable device records")
                except Exception as exc:
                    logger.warning(f"Failed to update applicable devices for guide {update['guide_uuid'][:8]}: {exc}")
            
            try:
                db_client._connection.commit()
                logger.info(f"✓ Updated applicable devices for {update_count} guides")
            except Exception as exc:
                logger.warning(f"Error committing applicable devices updates: {exc}")
        
        # Verify what was written
        try:
            db_client._ensure_connection()
            db_client._cursor.execute("SELECT COUNT(*) FROM knowledge_sources WHERE source_type = %s", ('ifixit',))
            actual_count = db_client._cursor.fetchone()[0]
            logger.info(f"✓ Verified: {actual_count} guides found in database with source_type='ifixit'")
        except Exception as exc:
            logger.warning(f"Could not verify database writes: {exc}")
    else:
        logger.warning("No guides found in JSON file!")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        logger.error("Usage: python load_json_to_db.py <json_file_path>")
        logger.error("Example: python load_json_to_db.py state/guides_data_household.json")
        sys.exit(1)
    
    json_path = Path(sys.argv[1])
    if not json_path.exists():
        logger.error(f"JSON file not found: {json_path}")
        sys.exit(1)
    
    try:
        db_client = DatabaseClient()
        logger.info("✓ Database connection established successfully")
    except DatabaseConnectionError as exc:
        logger.error(f"✗ Database connection failed: {exc}")
        logger.error("Please ensure DATABASE_URL is set in your environment or .env file")
        sys.exit(1)
    
    try:
        # Load JSON data
        guides_data = load_json_file(json_path)
        
        # Write to database
        write_guides_to_db(db_client, guides_data)
        
        logger.info("=" * 80)
        logger.info("✓ Successfully loaded JSON data to database")
        logger.info("=" * 80)
        
    except Exception as exc:
        logger.error(f"Error loading JSON to database: {exc}", exc_info=True)
        sys.exit(1)
    finally:
        try:
            db_client.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
