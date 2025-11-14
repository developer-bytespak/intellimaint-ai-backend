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
                if self.shutdown_requested:
                    logger.warning("Shutdown requested, cancelling remaining tasks")
                    break
                future = executor.submit(self._process_device, family_id, category_path, index, device)
                future_map[future] = (index, device)

            try:
                for future in concurrent.futures.as_completed(future_map):
                    if self.shutdown_requested:
                        logger.warning("Shutdown requested, cancelling remaining futures")
                        for f in future_map:
                            f.cancel()
                        break
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
                    except KeyboardInterrupt:
                        logger.warning("Interrupted by user, shutting down gracefully...")
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
            guides = self.api_client.get_guides(
                device_name=device_path,
                paginate=True,
                page_size=self.config.page_size,
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
        total_guides = len(guides)
        logger.info("Processing %d guides for device '%s'", total_guides, device_path)
        for idx, guide in enumerate(guides, 1):
            guide_id = guide.get("guideid")
            if guide_id is None:
                logger.debug("Skipping guide without guideid: %s", guide)
                continue

            try:
                logger.debug("Processing guide %d/%d (ID: %s) for device '%s'", idx, total_guides, guide_id, device_path)
                self._process_guide(model_id, guide)
                guide_count += 1
                last_guide_id = str(guide_id)
            except GuideProcessingError as exc:
                error_msg = f"Guide {guide_id} processing error: {exc}"
                logger.error(error_msg, exc_info=exc.original_error)
                guide_errors.append(error_msg)
            except Exception as exc:  # pylint: disable=broad-except
                error_msg = f"Guide {guide_id} failed: {exc}"
                logger.error(error_msg, exc_info=True)
                guide_errors.append(error_msg)

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

    def _process_guide(self, model_id: str, guide_summary: Dict[str, Any]) -> None:
        guide_id = guide_summary.get("guideid")
        if guide_id is None:
            raise GuideProcessingError(
                guide_id=None,
                device_path="unknown",
                message="Guide summary missing guideid",
            )

        try:
            guide_detail = self.api_client.get_guide_detail(int(guide_id))
            if guide_detail is None:
                raise GuideProcessingError(
                    guide_id=guide_id,
                    device_path="unknown",
                    message=f"Failed to fetch guide detail for guide_id {guide_id}",
                )
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
                    normalized_part["full_url"] = normalized_part["url"]  # Store both original and normalized
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
                # Document detail URL can be constructed
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
                    # Store full document data
                    doc_info["raw_data"] = doc
                else:
                    # If document is just an ID
                    doc_info["id"] = doc
                    doc_info["detail_url"] = f"https://www.ifixit.com/api/2.0/documents/{doc}"
                
                if doc_info:
                    document_urls.append(doc_info)

        # Build comprehensive metadata
        metadata = {
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
                # Guide-level tools and parts (with normalized URLs)
                "tools": guide_detail.get("tools") if guide_detail else None,
                "parts": normalized_parts if normalized_parts else None,
                # Step-level images
                "step_images": step_images if step_images else None,
                # Author information (with normalized URLs)
                "author": self._normalize_author_urls(guide_detail.get("author")) if guide_detail and guide_detail.get("author") else None,
                # Document URLs and download links
                "documents": document_urls if document_urls else None,
                "featured_document": featured_document_urls if featured_document_urls else None,
                # Additional metadata
                "flags": guide_detail.get("flags") if guide_detail else None,
                "prerequisites": guide_detail.get("prerequisites") if guide_detail else None,
                # Store raw documents array for reference
                "documents_raw": guide_detail.get("documents") if guide_detail else None,
                # Store summary for reference
                "summary_data": guide_summary,
            }
        }

        if not self.config.dry_run and self.db:
            # Final validation before database insertion
            if not raw_content or len(raw_content.strip()) < 10:
                logger.warning(f"Skipping guide {guide_id} - content too short or empty")
                return
            
            try:
                self.db.upsert_knowledge_source(
                    source_id=self._guide_uuid(str(guide_id)),
                    title=title,
                    raw_content=raw_content,
                    model_id=model_id,
                    word_count=word_count,
                    metadata=metadata,
                )
            except Exception as exc:
                raise GuideProcessingError(
                    guide_id=guide_id,
                    device_path="unknown",
                    message=f"Database error saving guide {guide_id}: {exc}",
                    original_error=exc,
                ) from exc

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


def signal_handler(signum, frame):
    """Handle interrupt signals gracefully."""
    logger.warning("Received interrupt signal (Ctrl+C), shutting down gracefully...")
    raise KeyboardInterrupt


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

