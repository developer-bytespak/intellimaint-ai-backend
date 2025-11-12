"""Checkpoint management for iFixit ingestion."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CHECKPOINT_DIR = Path(__file__).parent / "checkpoints"


class CheckpointWriter:
    """Writes periodic JSON checkpoints containing metrics and ledger state."""

    def __init__(self, directory: Path = DEFAULT_CHECKPOINT_DIR, interval: int = 50):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.interval = interval if interval and interval > 0 else None
        self._lock = RLock()
        self._counter = 0

    def maybe_write(self, metrics: Any, ledger: Any) -> None:
        """Write a checkpoint when the interval boundary is reached."""
        if not self.interval:
            return

        with self._lock:
            self._counter += 1
            if self._counter % self.interval != 0:
                return

            elapsed_attr = getattr(metrics, "elapsed_seconds", None)
            elapsed_value = elapsed_attr() if callable(elapsed_attr) else elapsed_attr

            snapshot = {
                "timestamp": datetime.utcnow().isoformat(),
                "metrics": {
                    "categories_processed": getattr(metrics, "categories_processed", None),
                    "devices_processed": getattr(metrics, "devices_processed", None),
                    "guides_processed": getattr(metrics, "guides_processed", None),
                    "errors": getattr(metrics, "errors", []),
                    "elapsed_seconds": elapsed_value,
                },
                "ledger": getattr(ledger, "as_dicts", lambda: [])(),
            }

            timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            path = self.directory / f"checkpoint_{timestamp}.json"

            with path.open("w", encoding="utf-8") as handle:
                json.dump(snapshot, handle, indent=2)

            logger.info("Checkpoint written to %s", path)

