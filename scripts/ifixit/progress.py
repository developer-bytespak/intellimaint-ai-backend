"""Progress tracking utilities for the iFixit collector."""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional, Set

logger = logging.getLogger(__name__)

DEFAULT_LEDGER_PATH = Path(__file__).parent / "state" / "ingest_state.csv"


@dataclass
class ProgressRecord:
    category_path: str
    status: str = "pending"  # pending | in_progress | complete | failed
    last_device_path: Optional[str] = None
    last_device_index: Optional[int] = None
    last_guide_id: Optional[str] = None
    total_devices_processed: int = 0
    total_guides_processed: int = 0
    retry_count: int = 0
    failed_devices: Set[str] = field(default_factory=set)
    last_error: Optional[str] = None
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_row(self) -> Dict[str, str]:
        return {
            "category_path": self.category_path,
            "status": self.status,
            "last_device_path": self.last_device_path or "",
            "last_device_index": str(self.last_device_index) if self.last_device_index is not None else "",
            "last_guide_id": self.last_guide_id or "",
            "total_devices_processed": str(self.total_devices_processed),
            "total_guides_processed": str(self.total_guides_processed),
            "retry_count": str(self.retry_count),
            "failed_devices": json.dumps(sorted(self.failed_devices)),
            "last_error": self.last_error or "",
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_row(cls, row: Dict[str, str]) -> "ProgressRecord":
        failed_devices = set()
        if row.get("failed_devices"):
            try:
                failed_devices = set(json.loads(row["failed_devices"]))
            except json.JSONDecodeError:
                logger.warning("Failed to decode failed_devices for row %s", row.get("category_path"))
        return cls(
            category_path=row["category_path"],
            status=row.get("status", "pending"),
            last_device_path=row.get("last_device_path") or None,
            last_device_index=int(row["last_device_index"]) if row.get("last_device_index") else None,
            last_guide_id=row.get("last_guide_id") or None,
            total_devices_processed=int(row.get("total_devices_processed") or 0),
            total_guides_processed=int(row.get("total_guides_processed") or 0),
            retry_count=int(row.get("retry_count") or 0),
            failed_devices=failed_devices,
            last_error=row.get("last_error") or None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row.get("updated_at") else datetime.utcnow(),
        )


class ProgressLedger:
    """CSV-backed ledger for resumable ingestion."""

    def __init__(self, ledger_path: Path = DEFAULT_LEDGER_PATH):
        self.ledger_path = Path(ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.records: Dict[str, ProgressRecord] = {}
        self._lock = RLock()

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def load(self) -> None:
        with self._lock:
            if not self.ledger_path.exists():
                logger.debug("Ledger file %s not found; starting fresh.", self.ledger_path)
                return

            with self.ledger_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    record = ProgressRecord.from_row(row)
                    self.records[record.category_path] = record
            logger.info("Loaded %s progress records from %s", len(self.records), self.ledger_path)

    def save(self) -> None:
        with self._lock:
            fieldnames = [
                "category_path",
                "status",
                "last_device_path",
                "last_device_index",
                "last_guide_id",
                "total_devices_processed",
                "total_guides_processed",
                "retry_count",
                "failed_devices",
                "last_error",
                "updated_at",
            ]
            temp_path = self.ledger_path.with_suffix(".tmp")
            with temp_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                for record in self.records.values():
                    writer.writerow(record.to_row())
            temp_path.replace(self.ledger_path)

    # ------------------------------------------------------------------ #
    # Record management
    # ------------------------------------------------------------------ #
    def get(self, category_path: str) -> ProgressRecord:
        with self._lock:
            if category_path not in self.records:
                self.records[category_path] = ProgressRecord(category_path=category_path)
            return self.records[category_path]

    def mark_category_started(self, category_path: str) -> None:
        with self._lock:
            record = self.get(category_path)
            record.status = "in_progress"
            record.updated_at = datetime.utcnow()
            self.save()

    def mark_category_complete(self, category_path: str) -> None:
        with self._lock:
            record = self.get(category_path)
            record.status = "complete"
            record.last_error = None
            record.updated_at = datetime.utcnow()
            record.failed_devices.clear()
            self.save()

    def record_device_success(
        self,
        category_path: str,
        device_path: str,
        device_index: int,
        guides_processed: int,
        last_guide_id: Optional[str],
    ) -> None:
        with self._lock:
            record = self.get(category_path)
            record.last_device_path = device_path
            record.last_device_index = device_index
            record.last_guide_id = last_guide_id
            record.total_devices_processed += 1
            record.total_guides_processed += guides_processed
            if device_path in record.failed_devices:
                record.failed_devices.remove(device_path)
            record.last_error = None
            record.updated_at = datetime.utcnow()
            self.save()

    def record_device_failure(
        self,
        category_path: str,
        device_path: str,
        device_index: int,
        error: str,
        last_guide_id: Optional[str] = None,
    ) -> None:
        with self._lock:
            record = self.get(category_path)
            record.last_device_path = device_path
            record.last_device_index = device_index
            record.last_guide_id = last_guide_id
            record.status = "failed"
            record.retry_count += 1
            record.failed_devices.add(device_path)
            record.last_error = error
            record.updated_at = datetime.utcnow()
            self.save()

    # ------------------------------------------------------------------ #
    # Introspection helpers
    # ------------------------------------------------------------------ #
    def categories_with_status(self, status: str) -> List[str]:
        with self._lock:
            return [path for path, record in self.records.items() if record.status == status]

    def get_failed_devices(self, category_path: str) -> List[str]:
        with self._lock:
            record = self.get(category_path)
            return sorted(record.failed_devices)

    def as_dicts(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    **asdict(record),
                    "failed_devices": sorted(record.failed_devices),
                    "updated_at": record.updated_at.isoformat(),
                }
                for record in self.records.values()
            ]


__all__ = ["ProgressLedger", "ProgressRecord", "DEFAULT_LEDGER_PATH"]

