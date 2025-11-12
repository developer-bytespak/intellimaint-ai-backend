# iFixit Storage & Upsert Mapping

This note documents how Phase 2 will persist iFixit data using the existing Prisma models (`EquipmentFamily`, `EquipmentModel`, `KnowledgeSource`) without schema changes.

## 1. Entity Mapping

| iFixit Entity | IntelliMaint Model | Key Fields |
|---------------|--------------------|------------|
| Category (path/title) | `EquipmentFamily` | `name` ← category title; `description` ← iFixit summary (if available); `metadata` JSON ← raw API payload including slug, url, breadcrumbs. |
| Device (namespace/title) | `EquipmentModel` | `modelName` ← device title; `modelNumber` ← parse from title if pattern like `Model XYZ`; `manufacturer` ← first token or extracted from metadata; `description` ← iFixit summary; `imageUrls` remains unused (no image ingest); `metadata` JSON ← iFixit identifiers/paths. |
| Guide | `KnowledgeSource` | `title` ← guide title; `sourceType` = `"ifixit"`; `rawContent` ← rendered markdown/HTML (text only, strip image binaries); `metadata` JSON stores `guideid`, `url`, `difficulty`, `time_required`, etc.; `wordCount` computed from text. |

## 2. Stable Identifiers & Upserts

- Generate deterministic UUIDv5 keys using the namespace UUID `6a9a2400-8a73-4894-8dbf-2ecb8d8b9a6d` (constant in collector):
  - Family key: `uuid5(namespace, f"ifixit/family/{category_path}")`.
  - Model key: `uuid5(namespace, f"ifixit/model/{device_path}")`.
  - Guide key: `uuid5(namespace, f"ifixit/guide/{guide_id}")`.
- Use Prisma upsert or SQL `INSERT ... ON CONFLICT (id)` to keep records idempotent.
- Store the iFixit `category_path`, `device_path`, and `guide_id` in each row's `metadata` JSON for audit and future lookups.

## 3. Sample SQL Upserts

```sql
INSERT INTO equipment_families (id, name, description, metadata)
VALUES ($1, $2, $3, $4)
ON CONFLICT (id) DO UPDATE
SET name = EXCLUDED.name,
    description = EXCLUDED.description,
    metadata = equipment_families.metadata || EXCLUDED.metadata;
```

```sql
INSERT INTO equipment_models (id, family_id, manufacturer, model_name, model_number, description, metadata)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (id) DO UPDATE
SET manufacturer = COALESCE(EXCLUDED.manufacturer, equipment_models.manufacturer),
    model_name = EXCLUDED.model_name,
    model_number = COALESCE(EXCLUDED.model_number, equipment_models.model_number),
    description = COALESCE(EXCLUDED.description, equipment_models.description),
    metadata = equipment_models.metadata || EXCLUDED.metadata;
```

```sql
INSERT INTO knowledge_sources (id, title, source_type, raw_content, model_id, word_count, metadata)
VALUES ($1, $2, 'ifixit', $3, $4, $5, $6)
ON CONFLICT (id) DO UPDATE
SET title = EXCLUDED.title,
    raw_content = EXCLUDED.raw_content,
    model_id = COALESCE(EXCLUDED.model_id, knowledge_sources.model_id),
    word_count = EXCLUDED.word_count,
    metadata = knowledge_sources.metadata || EXCLUDED.metadata,
    updated_at = NOW();
```

## 4. Image Handling

- The collector must **skip** downloading and storing images. Only textual content and metadata are persisted.
- `imageUrls` field on `EquipmentModel` can remain `NULL` or store an empty list (`[]`) for consistency.
- Guide steps that contain images will keep references in the text (e.g., Markdown image URLs), but no binary download occurs.

## 5. Operational Notes

- All writes occur inside a transaction per device to keep family/model/guide inserts consistent.
- Retry logic should be idempotent thanks to deterministic IDs.
- Metadata JSON structure example for a device:
  ```json
  {
    "ifixit": {
      "device_id": 12345,
      "path": "Phone/iPhone/iPhone 4",
      "url": "https://www.ifixit.com/Device/iPhone_4",
      "last_seen": "2025-11-10T23:16:01.876504"
    }
  }
  ```

This mapping satisfies Task 1 (`setup-storage`) and guides Phase 2 ingestion logic without schema updates or image collection.

