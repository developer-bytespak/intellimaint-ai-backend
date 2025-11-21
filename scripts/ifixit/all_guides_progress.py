"""Progress tracking for the all-guides approach."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Dict, Set

logger = logging.getLogger(__name__)

DEFAULT_PROGRESS_PATH = Path(__file__).parent / "state" / "all_guides_progress.json"


class AllGuidesProgress:
    """Tracks progress for the all-guides approach - stores processed guide IDs for resume."""

    def __init__(self, progress_path: Path = DEFAULT_PROGRESS_PATH):
        self.progress_path = Path(progress_path)
        self.progress_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self.processed_guide_ids: Set[int] = set()
        self.last_guide_index: int = 0
        self.total_guides_fetched: int = 0
        self.guides_processed: int = 0
        self.guides_skipped: int = 0
        self.errors: list[str] = []
        self.failed_guide_ids: Set[int] = set()
        self.start_time: datetime = datetime.utcnow()
        self.last_updated: datetime = datetime.utcnow()

    def load(self) -> None:
        """Load progress from JSON file."""
        with self._lock:
            if not self.progress_path.exists():
                logger.debug("Progress file %s not found; starting fresh.", self.progress_path)
                return

            try:
                with self.progress_path.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
                    self.processed_guide_ids = set(data.get("processed_guide_ids", []))
                    self.last_guide_index = data.get("last_guide_index", 0)
                    self.total_guides_fetched = data.get("total_guides_fetched", 0)
                    self.guides_processed = data.get("guides_processed", 0)
                    self.guides_skipped = data.get("guides_skipped", 0)
                    self.errors = data.get("errors", [])
                    self.failed_guide_ids = set(data.get("failed_guide_ids", []))
                    if data.get("start_time"):
                        self.start_time = datetime.fromisoformat(data["start_time"])
                    if data.get("last_updated"):
                        self.last_updated = datetime.fromisoformat(data["last_updated"])
                logger.info(
                    "Loaded progress: %d processed guides, %d failed, last index: %d",
                    len(self.processed_guide_ids),
                    len(self.failed_guide_ids),
                    self.last_guide_index,
                )
            except Exception as exc:
                logger.warning("Failed to load progress file %s: %s", self.progress_path, exc)

    def save(self) -> None:
        """Save progress to JSON file. Handles file locking gracefully."""
        with self._lock:
            try:
                data = {
                    "processed_guide_ids": sorted(self.processed_guide_ids),
                    "last_guide_index": self.last_guide_index,
                    "total_guides_fetched": self.total_guides_fetched,
                    "guides_processed": self.guides_processed,
                    "guides_skipped": self.guides_skipped,
                    "errors": self.errors[-100:],  # Keep last 100 errors
                    "failed_guide_ids": sorted(self.failed_guide_ids),
                    "start_time": self.start_time.isoformat(),
                    "last_updated": self.last_updated.isoformat(),
                }
                temp_path = self.progress_path.with_suffix(".tmp")
                
                # Write to temp file
                with temp_path.open("w", encoding="utf-8") as handle:
                    json.dump(data, handle, indent=2)
                
                # Try atomic rename first (preferred)
                try:
                    temp_path.replace(self.progress_path)
                except (OSError, PermissionError) as exc:
                    # If rename fails (file locked), try direct write as fallback
                    logger.debug("Atomic rename failed (file may be locked), trying direct write: %s", exc)
                    try:
                        with self.progress_path.open("w", encoding="utf-8") as handle:
                            json.dump(data, handle, indent=2)
                        # Clean up temp file
                        if temp_path.exists():
                            temp_path.unlink()
                    except Exception as write_exc:
                        logger.warning("Direct write also failed: %s", write_exc)
                        raise exc  # Raise original error
            except Exception as exc:
                # Don't crash the script - just log the error
                logger.warning("Failed to save progress file %s: %s (progress will continue in memory)", 
                             self.progress_path, exc)

    def is_processed(self, guide_id: int) -> bool:
        """Check if a guide has been processed."""
        with self._lock:
            return guide_id in self.processed_guide_ids

    def mark_processed(self, guide_id: int, guide_index: int) -> None:
        """Mark a guide as processed."""
        with self._lock:
            self.processed_guide_ids.add(guide_id)
            self.last_guide_index = max(self.last_guide_index, guide_index)
            self.guides_processed += 1
            if guide_id in self.failed_guide_ids:
                self.failed_guide_ids.remove(guide_id)
            self.last_updated = datetime.utcnow()
            # Save less frequently to avoid file locking issues
            # Save every 10 guides or on important milestones
            if self.guides_processed % 10 == 0 or guide_index % 100 == 0:
                self.save()

    def mark_failed(self, guide_id: int, error: str) -> None:
        """Mark a guide as failed."""
        with self._lock:
            self.failed_guide_ids.add(guide_id)
            self.errors.append(f"Guide {guide_id}: {error}")
            self.last_updated = datetime.utcnow()
            # Save on failures (important to track)
            self.save()

    def mark_skipped(self, guide_id: int) -> None:
        """Mark a guide as skipped."""
        with self._lock:
            self.guides_skipped += 1
            self.last_updated = datetime.utcnow()

    def set_total_guides(self, total: int) -> None:
        """Set the total number of guides fetched."""
        with self._lock:
            self.total_guides_fetched = total
            self.save()

    def get_stats(self) -> Dict:
        """Get current statistics."""
        with self._lock:
            return {
                "processed": len(self.processed_guide_ids),
                "failed": len(self.failed_guide_ids),
                "skipped": self.guides_skipped,
                "total_fetched": self.total_guides_fetched,
                "last_index": self.last_guide_index,
                "errors_count": len(self.errors),
            }


