#!/usr/bin/env python3
"""Database helper for iFixit ingestion."""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

import psycopg2
from psycopg2.extras import Json


class DatabaseConnectionError(RuntimeError):
    """Raised when the database connection cannot be established."""


@dataclass
class DatabaseConfig:
    dsn: Optional[str] = None
    application_name: str = "ifixit-collector"

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        return cls(
            dsn=os.getenv("DATABASE_URL"),
        )


class DatabaseClient:
    """Thin wrapper around psycopg2 for upsert operations."""

    def __init__(self, config: Optional[DatabaseConfig] = None):
        self.config = config or DatabaseConfig.from_env()
        if not self.config.dsn:
            raise DatabaseConnectionError(
                "DATABASE_URL is not set. Unable to connect to PostgreSQL."
            )
        self._connection: Optional[Any] = None
        self._cursor: Optional[Any] = None

    def _ensure_connection(self):
        """Ensure we have an active connection and cursor."""
        if self._connection is None or self._connection.closed:
            self._connection = psycopg2.connect(
                self.config.dsn,
                application_name=self.config.application_name,
            )
            self._cursor = self._connection.cursor()
    
    def close(self):
        """Close the persistent connection."""
        if self._cursor:
            try:
                self._cursor.close()
            except Exception:
                pass
            self._cursor = None
        if self._connection:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None

    @contextmanager
    def transaction(self):
        """Context manager for a transaction. Uses persistent connection if available."""
        # For backward compatibility, create a new connection if no persistent one exists
        if self._connection is None:
            conn = psycopg2.connect(
                self.config.dsn,
                application_name=self.config.application_name,
            )
            try:
                cursor = conn.cursor()
                try:
                    yield cursor
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    cursor.close()
            finally:
                conn.close()
        else:
            # Use persistent connection
            self._ensure_connection()
            try:
                yield self._cursor
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def __enter__(self):
        """Context manager entry - establish persistent connection."""
        self._ensure_connection()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - commit and close connection."""
        if self._connection and not self._connection.closed:
            if exc_type is None:
                try:
                    self._connection.commit()
                except Exception:
                    self._connection.rollback()
            else:
                self._connection.rollback()
        self.close()

    # ------------------------------------------------------------------ #
    # Upsert helpers
    # ------------------------------------------------------------------ #
    def upsert_equipment_family(
        self,
        family_id: str,
        name: str,
        description: Optional[str],
        metadata: Dict[str, Any],
    ) -> None:
        sql = """
        INSERT INTO equipment_families (id, name, description, metadata)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE
        SET name = EXCLUDED.name,
            description = COALESCE(EXCLUDED.description, equipment_families.description),
            metadata = equipment_families.metadata || EXCLUDED.metadata;
        """
        with self.transaction() as cur:
            cur.execute(sql, (family_id, name, description, Json(metadata)))

    def upsert_equipment_model(
        self,
        model_id: str,
        family_id: str,
        manufacturer: Optional[str],
        model_name: Optional[str],
        model_number: Optional[str],
        description: Optional[str],
        metadata: Dict[str, Any],
        image_urls: Optional[Iterable[str]] = None,
    ) -> None:
        sql = """
        INSERT INTO equipment_models (id, family_id, manufacturer, model_name, model_number, description, image_urls, metadata)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE
        SET manufacturer = COALESCE(EXCLUDED.manufacturer, equipment_models.manufacturer),
            model_name = COALESCE(EXCLUDED.model_name, equipment_models.model_name),
            model_number = COALESCE(EXCLUDED.model_number, equipment_models.model_number),
            description = COALESCE(EXCLUDED.description, equipment_models.description),
            image_urls = COALESCE(EXCLUDED.image_urls, equipment_models.image_urls),
            metadata = equipment_models.metadata || EXCLUDED.metadata;
        """
        image_payload: Optional[Any] = None
        if image_urls is not None:
            image_payload = Json(list(image_urls))

        with self.transaction() as cur:
            cur.execute(
                sql,
                (
                    model_id,
                    family_id,
                    manufacturer,
                    model_name,
                    model_number,
                    description,
                    image_payload,
                    Json(metadata),
                ),
            )

    def upsert_knowledge_source(
        self,
        source_id: str,
        title: str,
        raw_content: str,
        model_id: Optional[str],
        word_count: Optional[int],
        metadata: Dict[str, Any],
    ) -> None:
        # For upserts, we need to merge applicable_devices arrays
        # First, check if record exists and get existing metadata
        self._ensure_connection()
        
        self._cursor.execute(
            "SELECT metadata FROM knowledge_sources WHERE id = %s",
            (source_id,),
        )
        existing_row = self._cursor.fetchone()
        
        if existing_row and existing_row[0]:
            # Merge applicable_devices arrays
            # Handle JSONB which might be dict or need conversion
            existing_meta_raw = existing_row[0]
            if hasattr(existing_meta_raw, '__dict__'):
                existing_metadata = dict(existing_meta_raw)
            elif isinstance(existing_meta_raw, dict):
                existing_metadata = existing_meta_raw
            else:
                import json
                existing_metadata = json.loads(str(existing_meta_raw)) if existing_meta_raw else {}
            
            existing_ifixit = existing_metadata.get("ifixit", {}) if existing_metadata else {}
            new_ifixit = metadata.get("ifixit", {})
            
            # Get existing applicable_devices
            existing_devices = existing_ifixit.get("applicable_devices", []) or []
            new_devices = new_ifixit.get("applicable_devices", []) or []
            
            # Merge and deduplicate by model_id
            device_map = {}
            for device in existing_devices:
                if device and isinstance(device, dict) and device.get("model_id"):
                    device_map[device["model_id"]] = device
            for device in new_devices:
                if device and isinstance(device, dict) and device.get("model_id"):
                    device_map[device["model_id"]] = device
            
            # Update metadata with merged devices
            merged_devices = list(device_map.values())
            
            # Merge rest of metadata (new overwrites old for most fields, but merge applicable_devices)
            merged_metadata = {
                "ifixit": {
                    **existing_ifixit,
                    **new_ifixit,
                    "applicable_devices": merged_devices if merged_devices else (new_devices if new_devices else existing_devices),
                }
            }
            metadata = merged_metadata
        
        # Now do the upsert
        # If title/content are empty, preserve existing values (for metadata-only updates)
        sql = """
        INSERT INTO knowledge_sources (id, title, source_type, raw_content, model_id, word_count, metadata, updated_at)
        VALUES (%s, %s, 'ifixit', %s, %s, %s, %s, NOW())
        ON CONFLICT (id) DO UPDATE
        SET title = CASE 
                WHEN EXCLUDED.title = '' THEN knowledge_sources.title 
                ELSE EXCLUDED.title 
            END,
            source_type = 'ifixit',
            raw_content = CASE 
                WHEN EXCLUDED.raw_content = '' THEN knowledge_sources.raw_content 
                ELSE EXCLUDED.raw_content 
            END,
            model_id = COALESCE(EXCLUDED.model_id, knowledge_sources.model_id),
            word_count = COALESCE(EXCLUDED.word_count, knowledge_sources.word_count),
            metadata = EXCLUDED.metadata,
            updated_at = NOW();
        """
        self._cursor.execute(
            sql,
            (
                source_id,
                title,
                raw_content,
                model_id,
                word_count,
                Json(metadata),
            ),
        )
        
        # Commit periodically (every 10 writes) to avoid long transactions
        # This will be handled by the caller's batch commit logic


__all__ = ["DatabaseClient", "DatabaseConfig", "DatabaseConnectionError"]

