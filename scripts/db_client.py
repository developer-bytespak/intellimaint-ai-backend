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

    @contextmanager
    def transaction(self):
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
        sql = """
        INSERT INTO knowledge_sources (id, title, source_type, raw_content, model_id, word_count, metadata, updated_at)
        VALUES (%s, %s, 'ifixit', %s, %s, %s, %s, NOW())
        ON CONFLICT (id) DO UPDATE
        SET title = EXCLUDED.title,
            raw_content = EXCLUDED.raw_content,
            model_id = COALESCE(EXCLUDED.model_id, knowledge_sources.model_id),
            word_count = EXCLUDED.word_count,
            metadata = knowledge_sources.metadata || EXCLUDED.metadata,
            updated_at = NOW();
        """
        with self.transaction() as cur:
            cur.execute(
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


__all__ = ["DatabaseClient", "DatabaseConfig", "DatabaseConnectionError"]

