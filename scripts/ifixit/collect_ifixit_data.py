#!/usr/bin/env python3
"""Collect full iFixit dataset (categories → devices → guides) without images."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import signal
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from uuid import UUID, uuid5

from scripts.db_client import DatabaseClient, DatabaseConnectionError

from .api_client import iFixitAPIClient
from .all_guides_progress import AllGuidesProgress
from .checkpoint import CheckpointWriter, DEFAULT_CHECKPOINT_DIR
from .config import DEFAULT_PAGE_SIZE  # This import loads .env file
from .progress import ProgressLedger, DEFAULT_LEDGER_PATH

logger = logging.getLogger(__name__)

IFIXIT_NAMESPACE = UUID("6a9a2400-8a73-4894-8dbf-2ecb8d8b9a6d")

# Global shutdown flag for immediate interrupt handling
_shutdown_requested_global = False


@dataclass
class CollectorConfig:
    categories: Optional[List[str]] = None
    device_paths: Optional[List[str]] = None
    device_filter: Optional[str] = None
    concurrency: int = 4
    page_size: int = DEFAULT_PAGE_SIZE
    max_devices_per_category: Optional[int] = None
    max_guides_per_device: Optional[int] = None
    dry_run: bool = False
    resume: bool = False
    retry_failed: bool = False
    retry_failed_guides: bool = False  # NEW: Retry failed guides (all-guides approach)
    checkpoint_interval: int = 50
    ledger_path: Path = DEFAULT_LEDGER_PATH
    checkpoint_dir: Path = DEFAULT_CHECKPOINT_DIR
    log_format: str = "text"
    use_all_guides_approach: bool = False  # NEW: Use efficient all-guides approach
    max_consecutive_duplicates: int = 100  # Stop early if this many consecutive duplicates (indicates end of relevant guides)


@dataclass
class CollectorMetrics:
    start_time: datetime = field(default_factory=datetime.utcnow)
    categories_processed: int = 0
    devices_processed: int = 0
    guides_processed: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def elapsed_seconds(self) -> float:
        return (datetime.utcnow() - self.start_time).total_seconds()


@dataclass
class DeviceResult:
    device_path: str
    device_index: int
    guides_processed: int
    last_guide_id: Optional[str] = None


class DeviceProcessingError(RuntimeError):
    """Error during device processing."""
    def __init__(
        self,
        category_path: str,
        device_path: str,
        device_index: int,
        message: str,
        last_guide_id: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.category_path = category_path
        self.device_path = device_path
        self.device_index = device_index
        self.last_guide_id = last_guide_id
        self.original_error = original_error


class GuideProcessingError(RuntimeError):
    """Error during guide processing."""
    def __init__(
        self,
        guide_id: Any,
        device_path: str,
        message: str,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.guide_id = guide_id
        self.device_path = device_path
        self.original_error = original_error


class APIError(RuntimeError):
    """Error from iFixit API."""
    def __init__(
        self,
        endpoint: str,
        message: str,
        status_code: Optional[int] = None,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.endpoint = endpoint
        self.status_code = status_code
        self.original_error = original_error


class Collector:
    """Main orchestration class."""

    def __init__(
        self,
        api_client: iFixitAPIClient,
        db_client: Optional[DatabaseClient],
        ledger: ProgressLedger,
        config: CollectorConfig,
    ):
        self.shutdown_requested = False
        self.api_client = api_client
        self.db = db_client
        self.ledger = ledger
        self.config = config
        self.metrics = CollectorMetrics()
        self.checkpoint_writer = CheckpointWriter(
            directory=config.checkpoint_dir,
            interval=config.checkpoint_interval,
        )
        # Track processed guides in this run to avoid duplicate API calls
        self._processed_guides: Set[int] = set()
        # Cache guide details to reuse when same guide applies to multiple devices
        self._guide_detail_cache: Dict[int, Dict[str, Any]] = {}
        # Progress tracker for all-guides approach
        self._all_guides_progress: Optional[AllGuidesProgress] = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def run(self) -> CollectorMetrics:
        logger.info("Starting iFixit data collection...")
        if self.config.resume or self.config.retry_failed:
            self.ledger.load()

        if self.config.use_all_guides_approach:
            logger.info("Using efficient 'all guides' approach - fetching all guides directly")
            return self._process_all_guides_approach()

        # Original per-device approach
        logger.info("Using per-device approach - querying guides per device")
        categories_tree = self.api_client.get_categories()
        top_level_categories = self._select_categories(categories_tree)

        for category_name, subtree in top_level_categories:
            try:
                self._process_category(category_name, subtree)
            except Exception as exc:  # pylint: disable=broad-except
                message = f"Category '{category_name}' failed: {exc}"
                logger.exception(message)
                self.metrics.errors.append(message)

        logger.info(
            "Collection finished: %s categories, %s devices, %s guides in %.1fs",
            self.metrics.categories_processed,
            self.metrics.devices_processed,
            self.metrics.guides_processed,
            self.metrics.elapsed_seconds,
        )
        return self.metrics

    # ------------------------------------------------------------------ #
    # All-guides approach (efficient)
    # ------------------------------------------------------------------ #
    def _process_all_guides_approach(self) -> CollectorMetrics:
        """
        Efficient approach: Fetch all guides directly, then match to devices by category.
        This is much faster than querying guides per device.
        
        Features:
        - Resume capability (tracks processed guide IDs)
        - Checkpoint writing for recovery
        - Error recovery with retry logic
        - Progress tracking
        """
        logger.info("=" * 80)
        logger.info("ALL-GUIDES APPROACH: Fetching all guides directly")
        logger.info("=" * 80)
        
        # Initialize progress tracker
        self._all_guides_progress = AllGuidesProgress()
        if self.config.resume:
            self._all_guides_progress.load()
            logger.info(
                "Resume mode: %d guides already processed, %d failed",
                len(self._all_guides_progress.processed_guide_ids),
                len(self._all_guides_progress.failed_guide_ids),
            )

        # Step 1: Build category and device mappings
        logger.info("Step 1: Building category and device mappings...")
        categories_tree = self.api_client.get_categories()
        top_level_categories = self._select_categories(categories_tree)

        # Build mapping: category_path -> (family_id, devices)
        category_to_devices: Dict[str, Tuple[str, List[Dict[str, Any]]]] = {}
        device_path_to_model: Dict[str, str] = {}  # device_path -> model_id

        for category_name, subtree in top_level_categories:
            if self.config.categories and category_name not in self.config.categories:
                logger.debug("Skipping category '%s' (filtered).", category_name)
                continue

            category_path = category_name
            family_id = self._family_uuid(category_path)
            devices = self._extract_devices_from_tree(subtree, prefix=category_path)

            if self.config.max_devices_per_category is not None:
                devices = devices[: self.config.max_devices_per_category]

            # Filter devices based on config
            filtered_devices = []
            for device in devices:
                device_path = device.get("path") or device.get("namespace") or ""
                if not device_path:
                    continue
                if not self._device_selected(device_path):
                    continue
                filtered_devices.append(device)
                # Store device path to model_id mapping
                model_id = self._model_uuid(device_path)
                device_path_to_model[device_path] = model_id

            if filtered_devices:
                category_to_devices[category_path] = (family_id, filtered_devices)
                logger.info("Category '%s': %d devices", category_path, len(filtered_devices))

        logger.info("Built mappings: %d categories, %d total devices", len(category_to_devices), len(device_path_to_model))
        self.metrics.categories_processed = len(category_to_devices)
        self.metrics.devices_processed = len(device_path_to_model)

        # Prepare device/family data for batch writing (defer DB writes until after collection)
        families_to_write: List[Dict[str, Any]] = []
        devices_to_write: List[Dict[str, Any]] = []
        
        for category_path, (family_id, filtered_devices) in category_to_devices.items():
            category_name = category_path
            metadata = {
                "ifixit": {
                    "path": category_path,
                    "device_count": len(filtered_devices),
                    "processed_at": datetime.utcnow().isoformat(),
                }
            }
            families_to_write.append({
                "family_id": family_id,
                "name": category_name,
                "description": None,
                "metadata": metadata,
            })
            
            for device in filtered_devices:
                device_path = device.get("path") or device.get("namespace") or device.get("name")
                device_title = device.get("title") or device_path.split("/")[-1]
                manufacturer, model_number = self._split_manufacturer_and_model(device_title)
                model_id = device_path_to_model[device_path]

                device_metadata = {
                    "ifixit": {
                        "path": device_path,
                        "title": device_title,
                        "raw": device,
                        "processed_at": datetime.utcnow().isoformat(),
                    }
                }
                devices_to_write.append({
                    "model_id": model_id,
                    "family_id": family_id,
                    "manufacturer": manufacturer,
                    "model_name": device_title,
                    "model_number": model_number,
                    "description": device.get("summary") or device.get("description"),
                    "metadata": device_metadata,
                    "image_urls": None,
                })

        # Step 2: Fetch guides directly
        # If filtering by category, try to use category filter in API (if supported)
        # Otherwise fetch all guides and filter later
        if self.config.categories and len(self.config.categories) == 1:
            category_filter = self.config.categories[0]
            logger.info("Step 2: Fetching guides for category '%s'...", category_filter)
        else:
            category_filter = None
            logger.info("Step 2: Fetching all guides directly (no device filter)...")
        
        global _shutdown_requested_global

        try:
            all_guides = self.api_client.get_guides(
                device_name=None,  # No device filter
                category=category_filter,  # Try category filter if single category
                paginate=True,
                page_size=self.config.page_size,
                max_pages=None,  # Fetch all available guides
            )
            logger.info("✅ Fetched %d guide summaries", len(all_guides))
        except Exception as exc:
            logger.error("Failed to fetch all guides: %s", exc)
            self.metrics.errors.append(f"Failed to fetch all guides: {exc}")
            return self.metrics

        if self.config.max_guides_per_device is not None:
            # Note: max_guides_per_device doesn't make sense here, but we'll use it as a total limit
            all_guides = all_guides[: self.config.max_guides_per_device]
            logger.info("Limited to %d guides (--max-guides-per-device)", len(all_guides))

        # Update progress with total guides
        self._all_guides_progress.set_total_guides(len(all_guides))
        
        # Step 3: Process each guide and match to devices
        logger.info("Step 3: Processing guides and matching to devices...")
        total_guides = len(all_guides)
        guide_count = 0
        skipped_count = 0
        error_count = 0
        
        # Resume from last position if resuming
        start_index = 0
        if self.config.resume and self._all_guides_progress.last_guide_index > 0:
            start_index = self._all_guides_progress.last_guide_index
            logger.info("Resuming from guide index %d", start_index)
        
        # Load processed guide IDs into memory for fast lookup
        if self.config.resume:
            self._processed_guides.update(self._all_guides_progress.processed_guide_ids)
        
        # If retry-failed mode, only process failed guides
        if self.config.retry_failed_guides:
            failed_ids = self._all_guides_progress.failed_guide_ids
            logger.info("Retry-failed-guides mode: will retry %d failed guides", len(failed_ids))
            if failed_ids:
                # Filter guides to only failed ones
                all_guides = [g for g in all_guides if g.get("guideid") in failed_ids]
                logger.info("Filtered to %d failed guides to retry", len(all_guides))
                self._all_guides_progress.failed_guide_ids.clear()  # Clear failed list, will re-add if they fail again
            else:
                logger.warning("No failed guides found to retry")
                return self.metrics

        # Store guides in local JSON file first, then write to DB after collection completes
        # This allows progress to show immediately (like dry-run) while collecting data
        local_storage_path = self.config.checkpoint_dir.parent / "state" / "guides_data.json"
        local_storage_path.parent.mkdir(parents=True, exist_ok=True)
        guides_to_write: List[Dict[str, Any]] = []
        applicable_devices_updates: List[Dict[str, Any]] = []  # For updating existing guides with new devices
        
        logger.info("Step 1 complete: %d families, %d devices prepared for batch writing", 
                   len(families_to_write), len(devices_to_write))

        for idx, guide_summary in enumerate(all_guides, 1):
            if _shutdown_requested_global or self.shutdown_requested:
                logger.warning("Shutdown requested, stopping guide processing")
                # Save progress before exiting
                self._all_guides_progress.save()
                break

            # Skip if resuming and we haven't reached the resume point
            if idx < start_index:
                continue

            guide_id = guide_summary.get("guideid")
            if guide_id is None:
                logger.debug("Skipping guide without guideid: %s", guide_summary)
                continue

            # Check if already processed (in-memory or from progress file)
            if guide_id in self._processed_guides or self._all_guides_progress.is_processed(guide_id):
                skipped_count += 1
                self._all_guides_progress.mark_skipped(guide_id)
                if skipped_count <= 5 or skipped_count % 100 == 0:
                    logger.info("Guide %d/%d (ID: %s) already processed, skipping", idx, total_guides, guide_id)
                continue

            # Find matching devices based on guide's category
            guide_category = guide_summary.get("category") or ""
            matching_devices = self._find_matching_devices(guide_category, category_to_devices, device_path_to_model)

            if not matching_devices:
                logger.debug("Guide %d (ID: %s, category='%s') has no matching devices, skipping", idx, guide_id, guide_category)
                # Still process the guide but without device linkage (for completeness)
                # Or skip it - let's skip for now to avoid orphaned guides
                continue

            # Process guide once, link to all matching devices
            try:
                # Log progress more frequently (every 10 guides) so user can see it's working
                if idx % 10 == 0 or idx == 1 or (idx % 100 == 0):
                    logger.info(
                        "Processing guide %d/%d (ID: %s, category='%s') - matches %d device(s)",
                        idx, total_guides, guide_id, guide_category, len(matching_devices)
                    )

                # Process guide with first matching device as primary model_id
                # Other devices will be added to applicable_devices metadata
                primary_device_path = matching_devices[0]["device_path"]
                primary_model_id = matching_devices[0]["model_id"]

                # Process guide and get data (without writing to DB yet)
                guide_data = self._process_guide_to_memory(primary_model_id, guide_summary, device_path=primary_device_path)

                if guide_data:
                    guides_to_write.append(guide_data)

                # Track applicable devices for other matching devices
                for device_info in matching_devices[1:]:
                    guide_uuid = self._guide_uuid(str(guide_id))
                    applicable_device_info = {
                        "model_id": device_info["model_id"],
                        "device_path": device_info["device_path"],
                    }
                    applicable_devices_updates.append({
                        "guide_uuid": guide_uuid,
                        "applicable_device_info": applicable_device_info,
                    })

                self._processed_guides.add(guide_id)
                self._all_guides_progress.mark_processed(guide_id, idx)
                guide_count += 1
                self.metrics.guides_processed += 1
                
                # Save to local storage periodically
                if guide_count % self.config.checkpoint_interval == 0:
                    self._save_guides_to_local_storage(
                        guides_to_write, applicable_devices_updates, local_storage_path,
                        families=families_to_write, devices=devices_to_write
                    )
                    self.checkpoint_writer.maybe_write(self.metrics, self.ledger)
                    stats = self._all_guides_progress.get_stats()
                    logger.info(
                        "Progress: %d/%d guides processed (%.1f%%) - %d saved to local storage",
                        stats["processed"],
                        total_guides,
                        (stats["processed"] / total_guides * 100) if total_guides > 0 else 0,
                        len(guides_to_write),
                    )

            except GuideProcessingError as exc:
                error_count += 1
                error_msg = f"Guide {guide_id} processing error: {exc}"
                logger.error(error_msg, exc_info=exc.original_error)
                self.metrics.errors.append(error_msg)
                self._all_guides_progress.mark_failed(guide_id, str(exc))
            except Exception as exc:  # pylint: disable=broad-except
                error_count += 1
                error_msg = f"Guide {guide_id} failed: {exc}"
                logger.error(error_msg, exc_info=True)
                self.metrics.errors.append(error_msg)
                self._all_guides_progress.mark_failed(guide_id, str(exc))

        # Save final batch to local storage (includes families and devices)
        if guides_to_write or families_to_write or devices_to_write:
            self._save_guides_to_local_storage(
                guides_to_write, applicable_devices_updates, local_storage_path,
                families=families_to_write, devices=devices_to_write
            )
            logger.info("✓ Saved to local storage: %d guides, %d families, %d devices -> %s", 
                       len(guides_to_write), len(families_to_write), len(devices_to_write), local_storage_path)

        # Now load from local storage and write to database
        if not self.config.dry_run and self.db:
            guides_data = self._load_guides_from_local_storage(local_storage_path)
            if guides_data:
                guides_to_write = guides_data.get("guides", [])
                applicable_devices_updates = guides_data.get("applicable_devices_updates", [])
                families_to_write = guides_data.get("families", [])
                devices_to_write = guides_data.get("devices", [])
            
            # Write families and devices first
            if families_to_write or devices_to_write:
                logger.info("=" * 80)
                logger.info("Writing %d families and %d devices to database...", 
                           len(families_to_write), len(devices_to_write))
                logger.info("=" * 80)
                
                self.db._ensure_connection()
                
                # Write families
                for family_data in families_to_write:
                    try:
                        self.db.upsert_equipment_family(
                            family_id=family_data["family_id"],
                            name=family_data["name"],
                            description=family_data["description"],
                            metadata=family_data["metadata"],
                        )
                    except Exception as exc:
                        logger.warning("Failed to write family %s: %s", family_data["family_id"][:8], exc)
                
                # Write devices
                device_count = 0
                for device_data in devices_to_write:
                    try:
                        self.db.upsert_equipment_model(
                            model_id=device_data["model_id"],
                            family_id=device_data["family_id"],
                            manufacturer=device_data["manufacturer"],
                            model_name=device_data["model_name"],
                            model_number=device_data["model_number"],
                            description=device_data["description"],
                            metadata=device_data["metadata"],
                            image_urls=device_data["image_urls"],
                        )
                        device_count += 1
                        if device_count % 50 == 0:
                            self.db._connection.commit()
                            logger.debug("Wrote %d devices", device_count)
                    except Exception as exc:
                        logger.warning("Failed to write device %s: %s", device_data["model_id"][:8], exc)
                
                # Final commit for families/devices
                try:
                    self.db._connection.commit()
                    logger.info("✓ Wrote %d families and %d devices to database", 
                               len(families_to_write), device_count)
                except Exception as exc:
                    logger.warning("Error committing families/devices: %s", exc)
            
            if guides_to_write:
                logger.info("=" * 80)
                logger.info("Writing %d guides to database in batches...", len(guides_to_write))
                logger.info("=" * 80)
                
                # Initialize database connection
                self.db._ensure_connection()
                
                BATCH_SIZE = 100  # Write 100 guides at a time
                total_written = 0
                
                for batch_start in range(0, len(guides_to_write), BATCH_SIZE):
                    batch_end = min(batch_start + BATCH_SIZE, len(guides_to_write))
                    batch = guides_to_write[batch_start:batch_end]
                    
                    try:
                        for guide_data in batch:
                            self.db.upsert_knowledge_source(
                                source_id=guide_data["source_id"],
                                title=guide_data["title"],
                                raw_content=guide_data["raw_content"],
                                model_id=guide_data["model_id"],
                                word_count=guide_data["word_count"],
                                metadata=guide_data["metadata"],
                            )
                        
                        # Commit batch
                        self.db._connection.commit()
                        total_written += len(batch)
                        
                        logger.info("💾 Wrote batch %d-%d to database (%d/%d total, %.1f%%)",
                                   batch_start + 1, batch_end, total_written, len(guides_to_write),
                                   (total_written / len(guides_to_write) * 100))
                        
                    except Exception as exc:
                        logger.error("Error writing batch %d-%d: %s", batch_start + 1, batch_end, exc, exc_info=True)
                        try:
                            self.db._connection.rollback()
                        except Exception:
                            pass
                        # Don't count failed batch in total_written
                        # Continue with next batch
                
                # Update applicable devices for existing guides
                if applicable_devices_updates:
                    logger.info("Updating applicable devices for %d guides...", len(applicable_devices_updates))
                    update_count = 0
                    for update in applicable_devices_updates:
                        try:
                            update_metadata = {
                                "ifixit": {
                                    "applicable_devices": [update["applicable_device_info"]]
                                }
                            }
                            self.db.upsert_knowledge_source(
                                source_id=update["guide_uuid"],
                                title="",  # Preserve existing
                                raw_content="",  # Preserve existing
                                model_id=None,  # Don't change primary
                                word_count=None,
                                metadata=update_metadata,
                            )
                            update_count += 1
                            if update_count % 50 == 0:
                                self.db._connection.commit()
                                logger.debug("Updated %d applicable device records", update_count)
                        except Exception as exc:
                            logger.warning("Failed to update applicable devices for guide %s: %s", 
                                         update["guide_uuid"][:8], exc)
                    
                    # Final commit for applicable devices updates
                    try:
                        self.db._connection.commit()
                        logger.info("✓ Updated applicable devices for %d guides", update_count)
                    except Exception as exc:
                        logger.warning("Error committing applicable devices updates: %s", exc)
                
                # Verify what was written
                try:
                    self.db._ensure_connection()
                    self.db._cursor.execute("SELECT COUNT(*) FROM knowledge_sources WHERE source_type = %s", ('ifixit',))
                    actual_count = self.db._cursor.fetchone()[0]
                    logger.info("✓ Verified: %d guides found in database with source_type='ifixit'", actual_count)
                    if actual_count != total_written:
                        logger.warning("⚠ Mismatch: Expected %d guides, but found %d in database", total_written, actual_count)
                except Exception as exc:
                    logger.warning("Could not verify database writes: %s", exc)
                
                # Close database connection
                try:
                    self.db.close()
                    logger.info("✓ Database connection closed")
                except Exception as exc:
                    logger.warning("Error closing database connection: %s", exc)
        elif self.config.dry_run:
            logger.info("DRY-RUN: Would write %d guides to database", len(guides_to_write))
        
        self.checkpoint_writer.maybe_write(self.metrics, self.ledger)
        self._all_guides_progress.save()
        
        stats = self._all_guides_progress.get_stats()
        logger.info("=" * 80)
        logger.info("ALL-GUIDES APPROACH COMPLETE")
        logger.info("  Total guides fetched: %d", total_guides)
        logger.info("  Guides processed: %d (this run: %d)", stats["processed"], guide_count)
        logger.info("  Guides skipped (duplicates): %d", skipped_count)
        logger.info("  Failed guides: %d", stats["failed"])
        logger.info("  Errors: %d", error_count)
        logger.info("  Categories: %d", self.metrics.categories_processed)
        logger.info("  Devices: %d", self.metrics.devices_processed)
        logger.info("  Time elapsed: %.1fs", self.metrics.elapsed_seconds)
        logger.info("=" * 80)
        
        if stats["failed"] > 0:
            logger.warning(
                "⚠️  %d guides failed. Run with --retry-failed to retry them.",
                stats["failed"]
            )

        return self.metrics

    def _find_matching_devices(
        self,
        guide_category: str,
        category_to_devices: Dict[str, Tuple[str, List[Dict[str, Any]]]],
        device_path_to_model: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """
        Find devices that match a guide's category.
        
        Matching logic:
        1. Exact match: guide_category == device_path (last segment)
        2. Partial match: guide_category in device_path
        3. Category match: guide_category matches category name
        """
        if not guide_category:
            return []

        matching = []
        guide_category_lower = guide_category.lower().strip()

        for category_path, (family_id, devices) in category_to_devices.items():
            # Check if guide category matches category name
            category_name_lower = category_path.lower()
            if guide_category_lower == category_name_lower or guide_category_lower in category_name_lower:
                # All devices in this category match
                for device in devices:
                    device_path = device.get("path") or device.get("namespace") or ""
                    if device_path and device_path in device_path_to_model:
                        matching.append({
                            "device_path": device_path,
                            "model_id": device_path_to_model[device_path],
                            "category_path": category_path,
                        })
                continue

            # Check each device in the category
            for device in devices:
                device_path = device.get("path") or device.get("namespace") or ""
                if not device_path or device_path not in device_path_to_model:
                    continue

                device_title = device.get("title") or device_path.split("/")[-1]
                device_path_lower = device_path.lower()
                device_title_lower = device_title.lower()

                # Match if:
                # 1. Guide category is in device path
                # 2. Guide category is in device title
                # 3. Device path ends with guide category
                if (guide_category_lower in device_path_lower or
                    guide_category_lower in device_title_lower or
                    device_path_lower.endswith(guide_category_lower) or
                    device_title_lower.endswith(guide_category_lower)):
                    matching.append({
                        "device_path": device_path,
                        "model_id": device_path_to_model[device_path],
                        "category_path": category_path,
                    })

        # Deduplicate by device_path
        seen = set()
        unique_matching = []
        for m in matching:
            if m["device_path"] not in seen:
                seen.add(m["device_path"])
                unique_matching.append(m)

        return unique_matching

    # ------------------------------------------------------------------ #
    # Category/device processing
    # ------------------------------------------------------------------ #
    def _process_category(self, category_name: str, subtree: Dict[str, Any]) -> None:
        category_path = category_name
        if self.config.categories and category_name not in self.config.categories:
            logger.debug("Skipping category '%s' (filtered).", category_name)
            return

        record = self.ledger.get(category_path)
        if record.status == "complete" and not (self.config.retry_failed and record.failed_devices):
            if self.config.resume or self.config.retry_failed:
                logger.info("Skipping category '%s' (already complete).", category_name)
                return

        if record.status == "failed" and not self.config.retry_failed:
            logger.info("Skipping failed category '%s' (rerun with --retry-failed to retry).", category_name)
            return

        family_id = self._family_uuid(category_path)
        devices = self._extract_devices_from_tree(subtree, prefix=category_path)
        if self.config.max_devices_per_category is not None:
            devices = devices[: self.config.max_devices_per_category]

        device_entries = list(enumerate(devices))
        if not device_entries:
            logger.info("No devices found under category '%s'.", category_name)
            self.metrics.categories_processed += 1
            self.ledger.mark_category_complete(category_path)
            return

        start_index = 0
        if self.config.resume and record.last_device_index is not None:
            start_index = record.last_device_index + 1

        failed_only = self.config.retry_failed and record.failed_devices
        failed_targets = set(record.failed_devices) if failed_only else set()

        tasks: List[Tuple[int, Dict[str, Any]]] = []
        for index, device in device_entries:
            device_path = device.get("path") or device.get("namespace") or ""
            if failed_only:
                if device_path not in failed_targets:
                    continue
            else:
                if index < start_index:
                    continue
            if not self._device_selected(device_path):
                continue
            tasks.append((index, device))

        if not tasks:
            if failed_only and not record.failed_devices:
                logger.info("No failed devices remain for category '%s'.", category_name)
                self.metrics.categories_processed += 1
                self.ledger.mark_category_complete(category_path)
            elif self.config.resume and record.status == "complete":
                logger.info("Category '%s' already processed.", category_name)
            else:
                logger.info(
                    "No matching devices to process for category '%s' (filters may exclude all devices).",
                    category_name,
                )
            return

        logger.info(
            "Processing category '%s' with %s devices (family_id=%s)",
            category_name,
            len(tasks),
            family_id,
        )

        self.metrics.categories_processed += 1
        self.ledger.mark_category_started(category_path)

        metadata = {
            "ifixit": {
                "path": category_path,
                "device_count": len(device_entries),
                "processed_at": datetime.utcnow().isoformat(),
            }
        }

        if not self.config.dry_run and self.db:
            self.db.upsert_equipment_family(
                family_id=family_id,
                name=category_name,
                description=None,
                metadata=metadata,
            )

        category_had_errors = False
        global _shutdown_requested_global

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.config.concurrency) as executor:
            future_map: Dict[concurrent.futures.Future[DeviceResult], Tuple[int, Dict[str, Any]]] = {}
            for index, device in tasks:
                if _shutdown_requested_global or self.shutdown_requested:
                    logger.warning("Shutdown requested, cancelling remaining tasks")
                    break
                future = executor.submit(self._process_device, family_id, category_path, index, device)
                future_map[future] = (index, device)

            try:
                # Use a loop with timeout to check shutdown flag frequently
                while future_map:
                    # Check shutdown flag before waiting
                    if _shutdown_requested_global or self.shutdown_requested:
                        logger.warning("Shutdown requested, cancelling remaining futures")
                        for f in future_map:
                            f.cancel()
                        break
                    
                    # Wait for next future with short timeout to allow frequent shutdown checks
                    done, not_done = concurrent.futures.wait(future_map, timeout=1.0, return_when=concurrent.futures.FIRST_COMPLETED)
                    if not done:
                        continue  # No futures completed, check shutdown flag again
                    
                    for future in done:
                        if _shutdown_requested_global or self.shutdown_requested:
                            logger.warning("Shutdown requested, cancelling remaining futures")
                            for f in future_map:
                                f.cancel()
                            break
                        
                        if future in future_map:
                            index, device = future_map.pop(future)
                            device_path = device.get("path") or device.get("namespace") or ""
                            try:
                                result = future.result()
                                self.metrics.devices_processed += 1
                                self.metrics.guides_processed += result.guides_processed
                                self.ledger.record_device_success(
                                    category_path=category_path,
                                    device_path=result.device_path,
                                    device_index=result.device_index,
                                    guides_processed=result.guides_processed,
                                    last_guide_id=result.last_guide_id,
                                )
                                logger.info(
                                    "Device completed",
                                    extra={
                                        "event": "device_complete",
                                        "context": {
                                            "category": category_path,
                                            "device_path": result.device_path,
                                            "guides_processed": result.guides_processed,
                                            "last_guide_id": result.last_guide_id,
                                        },
                                    },
                                )
                            except DeviceProcessingError as exc:
                                category_had_errors = True
                                message = f"Device '{exc.device_path}' failed: {exc}"
                                logger.error(message)
                                self.metrics.errors.append(message)
                                self.ledger.record_device_failure(
                                    exc.category_path,
                                    exc.device_path,
                                    exc.device_index,
                                    str(exc),
                                    last_guide_id=exc.last_guide_id,
                                )
                                logger.error(
                                    "Device failed",
                                    extra={
                                        "event": "device_failed",
                                        "context": {
                                            "category": exc.category_path,
                                            "device_path": exc.device_path,
                                            "device_index": exc.device_index,
                                            "last_guide_id": exc.last_guide_id,
                                            "error": str(exc),
                                        },
                                    },
                                )
                            except KeyboardInterrupt:
                                logger.warning("Interrupted by user, shutting down gracefully...")
                                _shutdown_requested_global = True
                                self.shutdown_requested = True
                                for f in future_map:
                                    f.cancel()
                                raise
                            except Exception as exc:  # pylint: disable=broad-except
                                category_had_errors = True
                                message = f"Device '{device_path}' failed: {exc}"
                                logger.exception(message)
                                self.metrics.errors.append(message)
                                self.ledger.record_device_failure(
                                    category_path,
                                    device_path,
                                    index,
                                    str(exc),
                                    last_guide_id=None,
                                )
                                logger.error(
                                    "Device failed",
                                    extra={
                                        "event": "device_failed",
                                        "context": {
                                            "category": category_path,
                                            "device_path": device_path,
                                            "device_index": index,
                                            "error": str(exc),
                                        },
                                    },
                                )
                    
                    if _shutdown_requested_global or self.shutdown_requested:
                        break
            except KeyboardInterrupt:
                logger.warning("Interrupted by user, shutting down gracefully...")
                _shutdown_requested_global = True
                self.shutdown_requested = True
                for f in future_map:
                    f.cancel()
                raise
            finally:
                self.checkpoint_writer.maybe_write(self.metrics, self.ledger)

        final_record = self.ledger.get(category_path)
        if not category_had_errors and not final_record.failed_devices:
            self.ledger.mark_category_complete(category_path)
            logger.info(
                "Category complete",
                extra={
                    "event": "category_complete",
                    "context": {
                        "category": category_name,
                        "devices_processed": final_record.total_devices_processed,
                        "guides_processed": final_record.total_guides_processed,
                    },
                },
            )
        else:
            logger.warning(
                "Category '%s' finished with outstanding errors (%s failed devices).",
                category_name,
                len(final_record.failed_devices),
            )

    def _process_device(
        self,
        family_id: str,
        category_path: str,
        device_index: int,
        device: Dict[str, Any],
    ) -> DeviceResult:
        device_path = device.get("path") or device.get("namespace") or device.get("name")
        if not device_path:
            raise DeviceProcessingError(category_path, "<unknown>", device_index, "Device missing path/namespace.")

        device_title = device.get("title") or device_path.split("/")[-1]
        model_id = self._model_uuid(device_path)
        manufacturer, model_number = self._split_manufacturer_and_model(device_title)

        device_metadata = {
            "ifixit": {
                "path": device_path,
                "title": device_title,
                "raw": device,
                "processed_at": datetime.utcnow().isoformat(),
            }
        }

        try:
            if not self.config.dry_run and self.db:
                self.db.upsert_equipment_model(
                    model_id=model_id,
                    family_id=family_id,
                    manufacturer=manufacturer,
                    model_name=device_title,
                    model_number=model_number,
                    description=device.get("summary") or device.get("description"),
                    metadata=device_metadata,
                    image_urls=None,  # Explicitly skip image ingestion.
                )
        except Exception as exc:  # pylint: disable=broad-except
            raise DeviceProcessingError(
                category_path,
                device_path,
                device_index,
                f"Database error saving device '{device_path}': {exc}",
                original_error=exc,
            ) from exc

        last_guide_id: Optional[str] = None
        try:
            # Fetch all guides for this device
            # max_pages=None means no limit - will fetch until API returns no more
            # The pagination will stop naturally when:
            #   - API returns fewer items than page_size (end of results)
            #   - API provides a total count and we reach it
            #   - Safety limit of 10,000 items (if total is unknown)
            guides = self.api_client.get_guides(
                device_name=device_path,
                paginate=True,
                page_size=self.config.page_size,
                max_pages=None,  # No limit - fetch all available guides
            )
        except Exception as exc:  # pylint: disable=broad-except
            raise DeviceProcessingError(
                category_path,
                device_path,
                device_index,
                f"Failed to fetch guides for device '{device_path}': {exc}",
                original_error=exc,
            ) from exc

        if self.config.max_guides_per_device is not None:
            guides = guides[: self.config.max_guides_per_device]

        guide_errors: List[str] = []
        guide_count = 0
        skipped_count = 0
        consecutive_duplicates = 0  # Track consecutive duplicates for early stopping
        total_guides = len(guides)
        logger.info("Processing %d guides for device '%s'", total_guides, device_path)
        for idx, guide in enumerate(guides, 1):
            guide_id = guide.get("guideid")
            if guide_id is None:
                logger.debug("Skipping guide without guideid: %s", guide)
                continue

            # If we've already processed this guide, just update metadata with new device
            # (same guide can apply to multiple devices, but we only need to fetch it once)
            if guide_id in self._processed_guides:
                skipped_count += 1
                consecutive_duplicates += 1
                
                # Early stopping: if we see too many consecutive duplicates, we've likely hit
                # the end of device-specific guides and are seeing generic guides
                if consecutive_duplicates >= self.config.max_consecutive_duplicates:
                    logger.info(
                        "⚠️  Stopping early: %d consecutive duplicates detected (likely end of device-specific guides). "
                        "Processed %d new guides, skipped %d duplicates for device '%s'",
                        consecutive_duplicates, guide_count, skipped_count, device_path
                    )
                    break
                
                if skipped_count <= 5 or skipped_count % 100 == 0:
                    logger.info("Guide %d/%d (ID: %s) already processed, updating applicable devices for device '%s'", idx, total_guides, guide_id, device_path)
                else:
                    logger.debug("Guide %d (ID: %s) already processed, updating applicable devices for device '%s'", idx, guide_id, device_path)
                # Update metadata to include this device without re-fetching guide
                if not self.config.dry_run and self.db and model_id and device_path:
                    try:
                        guide_uuid = self._guide_uuid(str(guide_id))
                        applicable_device_info = {
                            "model_id": model_id,
                            "device_path": device_path,
                        }
                        # Just update metadata with new device - db_client will merge it
                        update_metadata = {
                            "ifixit": {
                                "applicable_devices": [applicable_device_info]
                            }
                        }
                        # Use empty title/content - db_client will preserve existing values
                        self.db.upsert_knowledge_source(
                            source_id=guide_uuid,
                            title="",  # Will be preserved from existing record
                            raw_content="",  # Will be preserved from existing record
                            model_id=None,  # Don't change primary model_id
                            word_count=None,
                            metadata=update_metadata,
                        )
                    except Exception as exc:
                        logger.warning("Failed to update applicable devices for guide %d: %s", guide_id, exc)
                continue
            
            # Reset consecutive duplicates counter when we find a new guide
            consecutive_duplicates = 0

            try:
                logger.info("Processing guide %d/%d (ID: %s) for device '%s'", idx, total_guides, guide_id, device_path)
                self._process_guide(model_id, guide, device_path=device_path)
                self._processed_guides.add(guide_id)  # Mark as processed
                guide_count += 1
                last_guide_id = str(guide_id)
                logger.debug("Completed guide %d/%d (ID: %s)", idx, total_guides, guide_id)
            except GuideProcessingError as exc:
                error_msg = f"Guide {guide_id} processing error: {exc}"
                logger.error(error_msg, exc_info=exc.original_error)
                guide_errors.append(error_msg)
            except Exception as exc:  # pylint: disable=broad-except
                error_msg = f"Guide {guide_id} failed: {exc}"
                logger.error(error_msg, exc_info=True)
                guide_errors.append(error_msg)

        if skipped_count > 0:
            logger.info("✅ Skipped %d duplicate guide(s) for device '%s' (already processed for other devices) - saved %d API calls!", skipped_count, device_path, skipped_count)
        
        if guide_errors:
            raise DeviceProcessingError(
                category_path,
                device_path,
                device_index,
                f"{len(guide_errors)} guide(s) failed ({'; '.join(guide_errors[:5])})",
                last_guide_id=last_guide_id,
            )

        return DeviceResult(
            device_path=device_path,
            device_index=device_index,
            guides_processed=guide_count,
            last_guide_id=last_guide_id,
        )

    def _validate_guide_content(self, raw_content: str, title: str, guide_id: Any) -> None:
        """Validate guide content before database insertion."""
        if not raw_content or not raw_content.strip():
            raise ValueError(f"Guide {guide_id} has empty content")
        
        if len(raw_content.strip()) < 10:
            logger.warning(f"Guide {guide_id} has very short content ({len(raw_content)} chars)")
        
        if not title or not title.strip():
            logger.warning(f"Guide {guide_id} has empty or missing title")

    def _extract_guide_metadata(
        self, guide_id: int, guide_summary: Dict[str, Any], guide_detail: Dict[str, Any], 
        model_id: str, device_path: Optional[str]
    ) -> Dict[str, Any]:
        """Extract and build guide metadata - shared logic for all guide processing."""
        # Extract step-level images
        step_images = []
        if guide_detail:
            steps = guide_detail.get("steps", [])
            for step in steps:
                step_id = step.get("stepid")
                media = step.get("media", {})
                if media and media.get("type") == "image":
                    images = media.get("data", [])
                    for img in images:
                        step_images.append({
                            "step_id": step_id,
                            "image_id": img.get("id"),
                            "guid": img.get("guid"),
                            "urls": {
                                "thumbnail": self._normalize_url(img.get("thumbnail")),
                                "medium": self._normalize_url(img.get("medium")),
                                "large": self._normalize_url(img.get("large")),
                                "original": self._normalize_url(img.get("original")),
                            }
                        })

        # Normalize and extract all URLs from parts
        normalized_parts = None
        if guide_detail and guide_detail.get("parts"):
            normalized_parts = []
            for part in guide_detail.get("parts", []):
                normalized_part = dict(part)
                if "url" in normalized_part:
                    normalized_part["url"] = self._normalize_url(normalized_part["url"])
                    normalized_part["full_url"] = normalized_part["url"]
                normalized_parts.append(normalized_part)

        # Extract document URLs
        document_urls = []
        featured_document_urls = {}
        
        if guide_detail:
            # Extract featured document URLs
            featured_doc_embed = guide_detail.get("featured_document_embed_url")
            featured_doc_thumbnail = guide_detail.get("featured_document_thumbnail_url")
            featured_doc_id = guide_detail.get("featured_documentid")
            
            if featured_doc_embed:
                featured_document_urls["embed_url"] = self._normalize_url(featured_doc_embed)
            if featured_doc_thumbnail:
                featured_document_urls["thumbnail_url"] = self._normalize_url(featured_doc_thumbnail)
            if featured_doc_id:
                featured_document_urls["document_id"] = featured_doc_id
                featured_document_urls["detail_url"] = f"https://www.ifixit.com/api/2.0/documents/{featured_doc_id}"
            
            # Extract document URLs from documents array
            documents = guide_detail.get("documents", [])
            for doc in documents:
                doc_info = {}
                if isinstance(doc, dict):
                    doc_id = doc.get("id") or doc.get("documentid") or doc.get("guid")
                    if doc_id:
                        doc_info["id"] = doc_id
                        doc_info["detail_url"] = f"https://www.ifixit.com/api/2.0/documents/{doc_id}"
                    if "url" in doc:
                        doc_info["url"] = self._normalize_url(doc.get("url"))
                    if "download_url" in doc:
                        doc_info["download_url"] = self._normalize_url(doc.get("download_url"))
                    if "title" in doc:
                        doc_info["title"] = doc.get("title")
                    if "filename" in doc:
                        doc_info["filename"] = doc.get("filename")
                    doc_info["raw_data"] = doc
                else:
                    doc_info["id"] = doc
                    doc_info["detail_url"] = f"https://www.ifixit.com/api/2.0/documents/{doc}"
                
                if doc_info:
                    document_urls.append(doc_info)

        # Build comprehensive metadata
        applicable_device_info = {
            "model_id": model_id,
            "device_path": device_path,
        } if model_id and device_path else None
        
        return {
            "ifixit": {
                "guide_id": guide_id,
                "url": self._normalize_url(guide_summary.get("url") or (guide_detail.get("url") if guide_detail else None)),
                "difficulty": guide_summary.get("difficulty") or (guide_detail.get("difficulty") if guide_detail else None),
                "time_required": guide_summary.get("time_required") or (guide_detail.get("time_required") if guide_detail else None),
                "time_required_min": guide_detail.get("time_required_min") if guide_detail else None,
                "time_required_max": guide_summary.get("time_required_max") or (guide_detail.get("time_required_max") if guide_detail else None),
                "type": guide_summary.get("type") or (guide_detail.get("type") if guide_detail else None),
                "subject": guide_summary.get("subject") or (guide_detail.get("subject") if guide_detail else None),
                "locale": guide_summary.get("locale") or (guide_detail.get("locale") if guide_detail else None),
                "revisionid": guide_summary.get("revisionid") or (guide_detail.get("revisionid") if guide_detail else None),
                "modified_date": guide_summary.get("modified_date") or (guide_detail.get("modified_date") if guide_detail else None),
                "tools": guide_detail.get("tools") if guide_detail else None,
                "parts": normalized_parts if normalized_parts else None,
                "step_images": step_images if step_images else None,
                "author": self._normalize_author_urls(guide_detail.get("author")) if guide_detail and guide_detail.get("author") else None,
                "documents": document_urls if document_urls else None,
                "featured_document": featured_document_urls if featured_document_urls else None,
                "flags": guide_detail.get("flags") if guide_detail else None,
                "prerequisites": guide_detail.get("prerequisites") if guide_detail else None,
                "documents_raw": guide_detail.get("documents") if guide_detail else None,
                "summary_data": guide_summary,
                "applicable_devices": [applicable_device_info] if applicable_device_info else None,
            }
        }

    def _process_guide_to_memory(
        self, model_id: str, guide_summary: Dict[str, Any], device_path: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Process guide and return data for batch writing.
        Returns None if guide should be skipped (e.g., content too short).
        """
        guide_id = guide_summary.get("guideid")
        if guide_id is None:
            raise GuideProcessingError(
                guide_id=None,
                device_path="unknown",
                message="Guide summary missing guideid",
            )

        # Check cache first to avoid duplicate API calls
        if guide_id in self._guide_detail_cache:
            guide_detail = self._guide_detail_cache[guide_id]
            logger.debug("Using cached guide detail for guide %d", guide_id)
        else:
            try:
                guide_detail = self.api_client.get_guide_detail(int(guide_id))
                if guide_detail is None:
                    raise GuideProcessingError(
                        guide_id=guide_id,
                        device_path="unknown",
                        message=f"Failed to fetch guide detail for guide_id {guide_id}",
                    )
                # Cache the guide detail for reuse
                self._guide_detail_cache[guide_id] = guide_detail
            except Exception as exc:
                raise GuideProcessingError(
                    guide_id=guide_id,
                    device_path="unknown",
                    message=f"API error fetching guide detail for guide_id {guide_id}: {exc}",
                    original_error=exc,
                ) from exc

        try:
            raw_content = self._render_guide_content(guide_summary, guide_detail)
            word_count = self._word_count(raw_content)
            
            # Validate content before processing
            title = guide_summary.get("title", f"Guide {guide_id}")
            self._validate_guide_content(raw_content, title, guide_id)
        except ValueError as exc:
            raise GuideProcessingError(
                guide_id=guide_id,
                device_path="unknown",
                message=f"Content validation failed for guide {guide_id}: {exc}",
                original_error=exc,
            ) from exc

        # Skip if content is too short
        if not raw_content or len(raw_content.strip()) < 10:
            logger.warning(f"Skipping guide {guide_id} - content too short or empty")
            return None

        # Extract metadata using shared method
        metadata = self._extract_guide_metadata(guide_id, guide_summary, guide_detail, model_id, device_path)

        # Return data for batch writing
        return {
            "source_id": self._guide_uuid(str(guide_id)),
            "title": title,
            "raw_content": raw_content,
            "model_id": model_id,
            "word_count": word_count,
            "metadata": metadata,
        }

    def _save_guides_to_local_storage(
        self, 
        guides: List[Dict[str, Any]], 
        applicable_devices_updates: List[Dict[str, Any]], 
        storage_path: Path,
        families: Optional[List[Dict[str, Any]]] = None,
        devices: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Save guides, families, and devices to local JSON file for persistence."""
        try:
            data = {
                "guides": guides,
                "applicable_devices_updates": applicable_devices_updates,
                "families": families or [],
                "devices": devices or [],
                "saved_at": datetime.utcnow().isoformat(),
                "count": len(guides),
            }
            temp_path = storage_path.with_suffix(".tmp")
            
            # Write to temp file
            with temp_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Try atomic rename first (preferred)
            try:
                temp_path.replace(storage_path)
            except (OSError, PermissionError) as exc:
                # If rename fails (file locked), try direct write as fallback
                logger.debug("Atomic rename failed (file may be locked), trying direct write: %s", exc)
                try:
                    with storage_path.open("w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    # Clean up temp file
                    if temp_path.exists():
                        temp_path.unlink()
                except Exception as write_exc:
                    logger.warning("Direct write also failed: %s", write_exc)
                    raise exc  # Raise original error
        except Exception as exc:
            logger.warning("Failed to save guides to local storage: %s (data remains in memory)", exc)

    def _load_guides_from_local_storage(self, storage_path: Path) -> Optional[Dict[str, Any]]:
        """Load guides from local JSON file."""
        if not storage_path.exists():
            return None
        try:
            with storage_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Failed to load guides from local storage: %s", exc)
            return None

    def _process_guide(self, model_id: str, guide_summary: Dict[str, Any], device_path: Optional[str] = None) -> None:
        """Process guide and write directly to database (used by per-device approach)."""
        guide_data = self._process_guide_to_memory(model_id, guide_summary, device_path)
        if not guide_data:
            return  # Skipped due to validation
        
        if not self.config.dry_run and self.db:
            try:
                self.db.upsert_knowledge_source(
                    source_id=guide_data["source_id"],
                    title=guide_data["title"],
                    raw_content=guide_data["raw_content"],
                    model_id=guide_data["model_id"],
                    word_count=guide_data["word_count"],
                    metadata=guide_data["metadata"],
                )
            except Exception as exc:
                raise GuideProcessingError(
                    guide_id=guide_summary.get("guideid"),
                    device_path="unknown",
                    message=f"Database error saving guide: {exc}",
                    original_error=exc,
                ) from exc
        elif self.config.dry_run:
            logger.debug(f"DRY-RUN: Would save guide {guide_summary.get('guideid')} to database")
        elif not self.db:
            logger.error(f"ERROR: Cannot save guide {guide_summary.get('guideid')} - db_client is None (not in dry-run mode)!")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _select_categories(self, categories_tree: Dict[str, Any]) -> List[tuple[str, Dict[str, Any]]]:
        items: List[tuple[str, Dict[str, Any]]] = []
        for name, subtree in categories_tree.items():
            if isinstance(subtree, dict):
                items.append((name, subtree))
        return items

    def _extract_devices_from_tree(self, tree: Dict[str, Any], prefix: str = "") -> List[Dict[str, Any]]:
        devices: List[Dict[str, Any]] = []
        for key, value in tree.items():
            current_path = f"{prefix}/{key}" if prefix else key
            if value is None:
                devices.append(
                    {
                        "title": key,
                        "namespace": current_path,
                        "path": current_path,
                    }
                )
            elif isinstance(value, dict):
                devices.extend(self._extract_devices_from_tree(value, current_path))
        return devices

    def _device_selected(self, device_path: str) -> bool:
        if self.config.device_paths and device_path not in self.config.device_paths:
            return False
        if self.config.device_filter and self.config.device_filter.lower() not in device_path.lower():
            return False
        return True

    @staticmethod
    def _split_manufacturer_and_model(title: str) -> tuple[Optional[str], Optional[str]]:
        if " " not in title:
            return None, title
        manufacturer = title.split(" ", 1)[0]
        return manufacturer, title

    @staticmethod
    def _render_guide_content(summary: Dict[str, Any], detail: Optional[Dict[str, Any]]) -> str:
        """Render guide content to markdown format."""
        lines: List[str] = []
        title = summary.get("title") or "Untitled Guide"
        lines.append(f"# {title}")

        # Add introduction from detail if available, otherwise from summary
        introduction = None
        if detail:
            introduction = detail.get("introduction_raw") or detail.get("introduction_rendered")
        if not introduction:
            introduction = summary.get("introduction") or summary.get("summary")
        
        if introduction:
            lines.extend(("", introduction))

        if detail:
            steps = detail.get("steps", [])
            for idx, step in enumerate(steps, start=1):
                step_title = step.get("title") or f"Step {idx}"
                if step_title.strip():
                    lines.extend(("", f"## {idx}. {step_title}"))
                else:
                    lines.extend(("", f"## Step {idx}"))
                
                # Process lines in the step
                for line in step.get("lines", []):
                    # iFixit API uses text_raw/text_rendered and bullet field
                    text = line.get("text_raw") or line.get("text_rendered") or line.get("text")
                    if not text:
                        continue
                    
                    bullet = line.get("bullet")
                    level = line.get("level", 0)
                    
                    # Handle different bullet types
                    if bullet == "icon_note" or bullet == "note":
                        lines.append(f"> **Note:** {text}")
                    elif bullet == "icon_warning" or bullet == "warning":
                        lines.append(f"> ⚠️ **Warning:** {text}")
                    elif bullet == "icon_caution" or bullet == "caution":
                        lines.append(f"> ⚠️ **Caution:** {text}")
                    elif bullet == "icon_tip" or bullet == "tip":
                        lines.append(f"> 💡 **Tip:** {text}")
                    elif bullet:
                        # Regular bullet point with indentation based on level
                        indent = "  " * level
                        lines.append(f"{indent}- {text}")
                    else:
                        # Plain text
                        indent = "  " * level
                        lines.append(f"{indent}{text}")
                
                # Add images for this step to the text content
                # Images are stored in step.media.data array
                media = step.get("media", {})
                if media and media.get("type") == "image":
                    images = media.get("data", [])
                    for img in images:
                        # Use original URL for full resolution, fallback to large/medium
                        image_url = (
                            Collector._normalize_url(img.get("original")) or
                            Collector._normalize_url(img.get("large")) or
                            Collector._normalize_url(img.get("medium")) or
                            Collector._normalize_url(img.get("thumbnail"))
                        )
                        if image_url:
                            # Add image reference in markdown format
                            # Include image ID and GUID for reference
                            img_id = img.get("id", "")
                            img_guid = img.get("guid", "")
                            alt_text = f"Step {idx} Image {img_id}" if img_id else f"Step {idx} Image"
                            lines.append(f"![{alt_text}]({image_url})")
                            # Also include all available image URLs as text for completeness
                            if img.get("thumbnail") or img.get("medium") or img.get("large") or img.get("original"):
                                lines.append(f"<!-- Image URLs: thumbnail={Collector._normalize_url(img.get('thumbnail'))}, medium={Collector._normalize_url(img.get('medium'))}, large={Collector._normalize_url(img.get('large'))}, original={image_url} -->")
            
            # Add conclusion if available
            conclusion = detail.get("conclusion_raw") or detail.get("conclusion_rendered")
            if conclusion:
                lines.extend(("", "## Conclusion", "", conclusion))
        else:
            # Fallback to summary if no detail available
            summary_text = summary.get("summary")
            if summary_text:
                lines.extend(("", summary_text))

        return "\n".join(lines)

    @staticmethod
    def _normalize_url(url: Optional[str]) -> Optional[str]:
        """Convert relative URLs to absolute iFixit URLs."""
        if not url:
            return None
        if url.startswith("http://") or url.startswith("https://"):
            return url
        if url.startswith("/"):
            return f"https://www.ifixit.com{url}"
        return url

    @staticmethod
    def _normalize_author_urls(author: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Normalize URLs in author information."""
        if not author:
            return None
        
        normalized = dict(author)
        if "url" in normalized:
            normalized["url"] = Collector._normalize_url(normalized["url"])
        
        # Normalize image URLs in author data
        if "image" in normalized and isinstance(normalized["image"], dict):
            image = normalized["image"]
            for key in ["mini", "thumbnail", "medium", "original", "full"]:
                if key in image and image[key]:
                    image[key] = Collector._normalize_url(image[key])
        
        return normalized

    @staticmethod
    def _word_count(content: str) -> int:
        return len([token for token in content.split() if token.strip()])

    @staticmethod
    def _family_uuid(category_path: str) -> str:
        return str(uuid5(IFIXIT_NAMESPACE, f"ifixit/family/{category_path}"))

    @staticmethod
    def _model_uuid(device_path: str) -> str:
        return str(uuid5(IFIXIT_NAMESPACE, f"ifixit/model/{device_path}"))

    @staticmethod
    def _guide_uuid(guide_id: str) -> str:
        return str(uuid5(IFIXIT_NAMESPACE, f"ifixit/guide/{guide_id}"))


# ---------------------------------------------------------------------- #
# CLI
# ---------------------------------------------------------------------- #
def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect iFixit data (text only).")
    parser.add_argument(
        "--category",
        action="append",
        help="Limit collection to specific top-level category (can be provided multiple times).",
    )
    parser.add_argument(
        "--device",
        action="append",
        help="Process only the specified device path(s) (exact match).",
    )
    parser.add_argument(
        "--device-filter",
        help="Collect only devices whose path contains the given substring.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Maximum number of devices processed concurrently.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help="Page size when fetching paginated guides.",
    )
    parser.add_argument(
        "--max-devices-per-category",
        type=int,
        help="Optional limit on devices processed per category (useful for testing).",
    )
    parser.add_argument(
        "--max-guides-per-device",
        type=int,
        help="Optional limit on guides processed per device (useful for testing).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from previously recorded progress.",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry devices recorded as failed in the progress ledger.",
    )
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        default=50,
        help="Write checkpoint snapshot after this many processed devices (set to 0 to disable).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run collection without writing to the database.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR).",
    )
    parser.add_argument(
        "--log-format",
        choices=["text", "json"],
        default="text",
        help="Log output format.",
    )
    parser.add_argument(
        "--use-all-guides-approach",
        action="store_true",
        help="Use efficient approach: fetch all guides directly, then match to devices by category. Much faster than per-device queries.",
    )
    parser.add_argument(
        "--retry-failed-guides",
        action="store_true",
        help="Retry only failed guides from previous run (works with --use-all-guides-approach).",
    )
    parser.add_argument(
        "--max-consecutive-duplicates",
        type=int,
        default=100,
        help="Stop early if this many consecutive duplicate guides are found (indicates end of device-specific guides). Default: 100.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        event = getattr(record, "event", None)
        if event:
            log_record["event"] = event
        context = getattr(record, "context", None)
        if context:
            log_record["context"] = context
        return json.dumps(log_record, ensure_ascii=False)


def configure_logging(level: str, log_format: str) -> None:
    root = logging.getLogger()
    root.handlers = []
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    handler = logging.StreamHandler()
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s"))
    root.addHandler(handler)


def write_failure_report(ledger: ProgressLedger, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    failures = []
    for record in ledger.as_dicts():
        failed_devices = record.get("failed_devices") or []
        if record.get("status") == "failed" or failed_devices:
            failures.append(
                {
                    "category_path": record.get("category_path"),
                    "status": record.get("status"),
                    "failed_devices": failed_devices,
                    "last_error": record.get("last_error"),
                    "last_device_path": record.get("last_device_path"),
                    "last_guide_id": record.get("last_guide_id"),
                    "updated_at": record.get("updated_at"),
                }
            )

    path = output_dir / "failed_devices.json"
    payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "failures": failures,
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    logger.info("Failure report written to %s", path)
    return path


_shutdown_count = 0

def signal_handler(signum, frame):
    """Handle interrupt signals gracefully."""
    global _shutdown_requested_global, _shutdown_count
    _shutdown_count += 1
    _shutdown_requested_global = True
    if _shutdown_count == 1:
        logger.warning("Received interrupt signal (Ctrl+C), shutting down gracefully...")
        raise KeyboardInterrupt
    else:
        # Force immediate exit on second Ctrl+C
        import sys
        logger.error("Force exit requested (Ctrl+C pressed %d times)", _shutdown_count)
        sys.exit(130)  # Standard exit code for SIGINT


def main(argv: Optional[Iterable[str]] = None) -> int:
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)
    
    args = parse_args(argv)
    configure_logging(args.log_level, args.log_format)

    config = CollectorConfig(
        categories=args.category,
        device_paths=args.device,
        device_filter=args.device_filter,
        concurrency=max(1, args.concurrency),
        page_size=args.page_size,
        max_devices_per_category=args.max_devices_per_category,
        max_guides_per_device=args.max_guides_per_device,
        dry_run=args.dry_run,
        resume=args.resume,
        retry_failed=args.retry_failed,
        checkpoint_interval=args.checkpoint_interval,
        log_format=args.log_format,
        use_all_guides_approach=args.use_all_guides_approach,
        retry_failed_guides=args.retry_failed_guides,
        max_consecutive_duplicates=args.max_consecutive_duplicates,
    )

    api_client = iFixitAPIClient()
    ledger = ProgressLedger(config.ledger_path)

    if config.dry_run:
        db_client = None
        logger.info("=" * 80)
        logger.info("⚠️  DRY-RUN MODE: Database writes are DISABLED")
        logger.info("=" * 80)
    else:
        try:
            db_client = DatabaseClient()
            logger.info("✓ Database connection established successfully")
        except DatabaseConnectionError as exc:
            logger.error("=" * 80)
            logger.error("✗ Database connection failed: %s", exc)
            logger.error("=" * 80)
            logger.error("Please ensure DATABASE_URL is set in your environment or .env file")
            return 1

    collector = Collector(api_client=api_client, db_client=db_client, ledger=ledger, config=config)
    metrics = collector.run()
    
    # Final warning if in dry-run mode
    if config.dry_run:
        logger.warning("=" * 80)
        logger.warning("⚠️  DRY-RUN MODE: No data was written to the database!")
        logger.warning("Run without --dry-run to actually save data to the database")
        logger.warning("=" * 80)
    elif db_client is None:
        logger.error("=" * 80)
        logger.error("✗ WARNING: db_client is None but dry_run is False!")
        logger.error("This should not happen - no data was written to the database")
        logger.error("=" * 80)

    logger.info(
        "Summary: categories=%s devices=%s guides=%s errors=%s elapsed=%.1fs",
        metrics.categories_processed,
        metrics.devices_processed,
        metrics.guides_processed,
        len(metrics.errors),
        metrics.elapsed_seconds,
    )

    if metrics.errors:
        logger.warning("Encountered %s errors during collection.", len(metrics.errors))
        for err in metrics.errors:
            logger.warning("  %s", err)

    write_failure_report(ledger, config.ledger_path.parent)

    return 0 if not metrics.errors else 2


if __name__ == "__main__":
    sys.exit(main())

