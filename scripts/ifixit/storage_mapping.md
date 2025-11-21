# iFixit Storage & Upsert Mapping

This note documents how Phase 2 will persist iFixit data using the existing Prisma models (`EquipmentFamily`, `EquipmentModel`, `KnowledgeSource`) without schema changes.

## 1. Entity Mapping

| iFixit Entity | IntelliMaint Model | Key Fields |
|---------------|--------------------|------------|
| Category (path/title) | `EquipmentFamily` | `name` ← category title; `description` ← iFixit summary (if available); `metadata` JSON ← raw API payload including slug, url, breadcrumbs. |
| Device (namespace/title) | `EquipmentModel` | `modelName` ← device title; `modelNumber` ← parse from title if pattern like `Model XYZ`; `manufacturer` ← first token or extracted from metadata; `description` ← iFixit summary; `imageUrls` remains unused (no image ingest); `metadata` JSON ← iFixit identifiers/paths. |
| Guide | `KnowledgeSource` | `title` ← guide title; `sourceType` = `"ifixit"`; `rawContent` ← rendered markdown (text only, no image binaries); `metadata` JSON stores comprehensive guide data including `guideid`, `url`, `difficulty`, `time_required`, `tools`, `parts`, `step_images`, `author`, `flags`, `prerequisites`, `documents`, etc.; `wordCount` computed from text. |

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

- The collector **does not download** image binaries. Only textual content and metadata are persisted.
- `imageUrls` field on `EquipmentModel` remains `NULL` (no image ingestion).
- Guide step images are stored as URLs in the `metadata.step_images` array with structure:
  ```json
  {
    "step_id": 1,
    "image_id": 12345,
    "guid": "abc123",
    "urls": {
      "thumbnail": "https://...",
      "medium": "https://...",
      "large": "https://...",
      "original": "https://..."
    }
  }
  ```
- Image URLs are preserved in metadata for future reference, but no binary download occurs.

## 5. Metadata Structure

### Guide Metadata Example
```json
{
  "ifixit": {
    "guide_id": 12345,
    "url": "https://www.ifixit.com/Guide/...",
    "difficulty": "Easy",
    "time_required": "15 minutes",
    "time_required_min": 10,
    "time_required_max": 20,
    "type": "replacement",
    "subject": "Keyboard",
    "locale": "en",
    "revisionid": 1357831,
    "modified_date": 1736973864,
    "tools": [...],
    "parts": [...],
    "step_images": [
      {
        "step_id": 1,
        "image_id": 233436,
        "guid": "H5wkkFSj1tYhJdrg",
        "urls": {...}
      }
    ],
    "author": {
      "userid": 1,
      "username": "iRobot",
      ...
    },
    "flags": [...],
    "prerequisites": [...],
    "documents": [...],
    "summary_data": {...}
  }
}
```

### Device Metadata Example
```json
{
  "ifixit": {
    "path": "Phone/iPhone/iPhone 4",
    "title": "iPhone 4",
    "raw": {...},
    "processed_at": "2025-11-14T01:30:00.000000"
  }
}
```

## 6. Operational Notes

- All writes occur inside a transaction per device to keep family/model/guide inserts consistent.
- Retry logic is idempotent thanks to deterministic UUIDs.
- Content validation ensures minimum content length (10 characters) before insertion.
- Enhanced error handling provides specific error types: `DeviceProcessingError`, `GuideProcessingError`, `APIError`.
- Guide content rendering handles all iFixit line types: text, bullets, notes, warnings, cautions, tips with proper markdown formatting.

This mapping reflects the actual implementation and guides ingestion logic without schema updates or image collection.

