#!/usr/bin/env python3
"""Collect full iFixit dataset (categories → devices → guides) without images."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import UUID, uuid5

from scripts.db_client import DatabaseClient, DatabaseConnectionError

from .api_client import iFixitAPIClient
from .checkpoint import CheckpointWriter, DEFAULT_CHECKPOINT_DIR
from .config import DEFAULT_PAGE_SIZE
from .progress import ProgressLedger, DEFAULT_LEDGER_PATH

logger = logging.getLogger(__name__)

IFIXIT_NAMESPACE = UUID("6a9a2400-8a73-4894-8dbf-2ecb8d8b9a6d")


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
    checkpoint_interval: int = 50
    ledger_path: Path = DEFAULT_LEDGER_PATH
    checkpoint_dir: Path = DEFAULT_CHECKPOINT_DIR
    log_format: str = "text"


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
    def __init__(
        self,
        category_path: str,
        device_path: str,
        device_index: int,
        message: str,
        last_guide_id: Optional[str] = None,
    ):
        super().__init__(message)
        self.category_path = category_path
        self.device_path = device_path
        self.device_index = device_index
        self.last_guide_id = last_guide_id


class Collector:
    """Main orchestration class."""

    def __init__(
        self,
        api_client: iFixitAPIClient,
        db_client: Optional[DatabaseClient],
        ledger: ProgressLedger,
        config: CollectorConfig,
    ):
        self.api_client = api_client
        self.db = db_client
        self.ledger = ledger
        self.config = config
        self.metrics = CollectorMetrics()
        self.checkpoint_writer = CheckpointWriter(
            directory=config.checkpoint_dir,
            interval=config.checkpoint_interval,
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def run(self) -> CollectorMetrics:
        logger.info("Starting iFixit data collection...")
        if self.config.resume or self.config.retry_failed:
            self.ledger.load()

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

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.config.concurrency) as executor:
            future_map: Dict[concurrent.futures.Future[DeviceResult], Tuple[int, Dict[str, Any]]] = {}
            for index, device in tasks:
                future = executor.submit(self._process_device, family_id, category_path, index, device)
                future_map[future] = (index, device)

            for future in concurrent.futures.as_completed(future_map):
                index, device = future_map[future]
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
            raise DeviceProcessingError(category_path, device_path, device_index, f"DB error: {exc}") from exc

        last_guide_id: Optional[str] = None
        try:
            guides = self.api_client.get_guides(
                device_name=device_path,
                paginate=True,
                page_size=self.config.page_size,
            )
        except Exception as exc:  # pylint: disable=broad-except
            raise DeviceProcessingError(category_path, device_path, device_index, f"Guide fetch failed: {exc}") from exc

        if self.config.max_guides_per_device is not None:
            guides = guides[: self.config.max_guides_per_device]

        guide_errors: List[str] = []
        guide_count = 0
        for guide in guides:
            guide_id = guide.get("guideid")
            if guide_id is None:
                logger.debug("Skipping guide without guideid: %s", guide)
                continue

            try:
                self._process_guide(model_id, guide)
                guide_count += 1
                last_guide_id = str(guide_id)
            except Exception as exc:  # pylint: disable=broad-except
                guide_errors.append(f"{guide_id}: {exc}")

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

    def _process_guide(self, model_id: str, guide_summary: Dict[str, Any]) -> None:
        guide_id = guide_summary.get("guideid")
        if guide_id is None:
            raise ValueError("Guide summary missing guideid.")

        guide_detail = self.api_client.get_guide_detail(int(guide_id))
        raw_content = self._render_guide_content(guide_summary, guide_detail)
        word_count = self._word_count(raw_content)

        metadata = {
            "ifixit": {
                "guide_id": guide_id,
                "url": guide_summary.get("url"),
                "difficulty": guide_summary.get("difficulty"),
                "time_required": guide_summary.get("time_required"),
                "tools": guide_detail.get("tools") if guide_detail else None,
                "parts": guide_detail.get("parts") if guide_detail else None,
                "summary": guide_summary,
            }
        }

        if not self.config.dry_run and self.db:
            self.db.upsert_knowledge_source(
                source_id=self._guide_uuid(str(guide_id)),
                title=guide_summary.get("title", f"Guide {guide_id}"),
                raw_content=raw_content,
                model_id=model_id,
                word_count=word_count,
                metadata=metadata,
            )

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
        lines: List[str] = []
        title = summary.get("title") or "Untitled Guide"
        lines.append(f"# {title}")

        introduction = summary.get("introduction")
        if introduction:
            lines.extend(("", introduction))

        if detail:
            steps = detail.get("steps", [])
            for idx, step in enumerate(steps, start=1):
                step_title = step.get("title") or f"Step {idx}"
                lines.extend(("", f"## {idx}. {step_title}"))
                for line in step.get("lines", []):
                    if line.get("type") == "text" and line.get("text"):
                        lines.append(line["text"])
                    elif line.get("type") == "bullet" and line.get("text"):
                        lines.append(f"- {line['text']}")
        else:
            summary_text = summary.get("summary")
            if summary_text:
                lines.extend(("", summary_text))

        return "\n".join(lines)

    @staticmethod
    def _word_count(content: str) -> int:
        return len([token for token in content.split() if token.strip()])

    @staticmethod
    def _family_uuid(category_path: str) -> str:
        return str(uuid5(IFIXIT_NAMESPACE, f"family:{category_path}"))

    @staticmethod
    def _model_uuid(device_path: str) -> str:
        return str(uuid5(IFIXIT_NAMESPACE, f"model:{device_path}"))

    @staticmethod
    def _guide_uuid(guide_id: str) -> str:
        return str(uuid5(IFIXIT_NAMESPACE, f"guide:{guide_id}"))


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


def main(argv: Optional[Iterable[str]] = None) -> int:
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
    )

    api_client = iFixitAPIClient()
    ledger = ProgressLedger(config.ledger_path)

    if config.dry_run:
        db_client = None
        logger.info("Running in dry-run mode; database writes are disabled.")
    else:
        try:
            db_client = DatabaseClient()
        except DatabaseConnectionError as exc:
            logger.error("Database connection failed: %s", exc)
            return 1

    collector = Collector(api_client=api_client, db_client=db_client, ledger=ledger, config=config)
    metrics = collector.run()

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

