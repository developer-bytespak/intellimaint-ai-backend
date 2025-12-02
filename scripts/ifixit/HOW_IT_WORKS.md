# How the iFixit Data Extraction System Works

## 📋 Table of Contents
1. [System Overview](#system-overview)
2. [Architecture Components](#architecture-components)
3. [Data Flow Step-by-Step](#data-flow-step-by-step)
4. [Where Data is Stored](#where-data-is-stored)
5. [Progress Tracking & Resumability](#progress-tracking--resumability)
6. [Database Schema & Relationships](#database-schema--relationships)
7. [Complete Example Walkthrough](#complete-example-walkthrough)

---

## System Overview

The iFixit collector is a **hierarchical data extraction system** that:
1. Fetches categories from iFixit API
2. Extracts devices from each category
3. Downloads guides for each device
4. Processes and stores everything in PostgreSQL

**Key Features:**
- ✅ Resumable (can stop and continue)
- ✅ Concurrent processing (multiple devices at once)
- ✅ Progress tracking (CSV + JSON checkpoints)
- ✅ Error handling with retry logic
- ✅ Complete content extraction (text + images + metadata)

---

## Architecture Components

### 1. **API Client** (`api_client.py`)
- Handles all HTTP requests to iFixit API
- Manages rate limiting (respects API limits)
- Implements retry logic with exponential backoff
- Paginates through large result sets

### 2. **Collector** (`collect_ifixit_data.py`)
- Main orchestration class
- Processes categories → devices → guides
- Renders content to markdown
- Generates deterministic UUIDs

### 3. **Database Client** (`db_client.py`)
- PostgreSQL connection wrapper
- Provides upsert operations (insert or update)
- Manages transactions

### 4. **Progress Ledger** (`progress.py`)
- CSV file tracking: `scripts/ifixit/state/ingest_state.csv`
- Tracks which categories/devices/guides are processed
- Enables resumability

### 5. **Checkpoint Writer** (`checkpoint.py`)
- JSON snapshots: `scripts/ifixit/checkpoints/checkpoint_*.json`
- Saves metrics and progress every N devices
- Used for recovery and monitoring

---

## Data Flow Step-by-Step

### Phase 1: Initialization

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Script Starts                                            │
│    python -m scripts.ifixit.collect_ifixit_data             │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Load Configuration                                       │
│    - Load DATABASE_URL from .env file                       │
│    - Initialize API client with rate limiting               │
│    - Connect to PostgreSQL database                         │
│    - Load progress ledger (if --resume)                     │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Fetch Categories Tree                                    │
│    GET https://www.ifixit.com/api/2.0/categories            │
│    Returns: Hierarchical tree of all categories             │
│    Example: {                                               │
│      "Phone": {                                             │
│        "iPhone": {                                          │
│          "iPhone 4": null,  ← This is a device              │
│          "iPhone 5": null                                   │
│        }                                                    │
│      }                                                      │
│    }                                                        │
└─────────────────────────────────────────────────────────────┘
```

### Phase 2: Category Processing

```
┌─────────────────────────────────────────────────────────────┐
│ 4. For Each Top-Level Category                              │
│    Example: "Phone"                                         │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Extract Devices from Category Tree                      │
│    Recursively walks the tree to find devices               │
│    Device = leaf node (value is null)                       │
│    Example: "Phone/iPhone/iPhone 4"                         │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Create Equipment Family (Category)                       │
│    - Generate UUID: uuid5(namespace, "ifixit/family/Phone")  │
│    - Store in: equipment_families table                     │
│    Fields:                                                  │
│      - id: UUID                                             │
│      - name: "Phone"                                         │
│      - description: null (or from API if available)          │
│      - metadata: JSON with category info                    │
└─────────────────────────────────────────────────────────────┘
```

### Phase 3: Device Processing (Concurrent)

```
┌─────────────────────────────────────────────────────────────┐
│ 7. Process Devices in Parallel (ThreadPoolExecutor)        │
│    Default: 4 concurrent devices                            │
│    Each device processed in separate thread                  │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 8. For Each Device (e.g., "iPhone 4")                       │
│    a) Create Equipment Model                                │
│       - Generate UUID: uuid5(namespace, "ifixit/model/...")  │
│       - Extract manufacturer: "Apple"                         │
│       - Extract model name: "iPhone 4"                      │
│       - Store in: equipment_models table                    │
│                                                              │
│    b) Fetch Guide List (Summaries Only)                     │
│       GET /api/2.0/guides?device=Phone/iPhone/iPhone%204     │
│       Returns: List of guide summaries (just IDs/titles)    │
│       Purpose: To know which guides exist for this device   │
│       Example: [                                             │
│         {"guideid": 12345, "title": "Screen Replacement"},  │
│         {"guideid": 12346, "title": "Battery Replacement"}  │
│       ]                                                      │
│       Paginated: 100 guides per page                        │
│                                                              │
│       ⚠️  NOTE: These are ONLY summaries, not full content! │
└─────────────────────────────────────────────────────────────┘
```

### Phase 4: Guide Processing

```
┌─────────────────────────────────────────────────────────────┐
│ 9. For Each Guide Summary                                   │
│    We use the summary ONLY to get the guide ID              │
│    Example: {                                               │
│      "guideid": 12345,                                      │
│      "title": "iPhone 4 Screen Replacement",               
│
│      "url": "/Guide/iPhone+4+Screen+Replacement/12345"       │
│    }                                                        │
│                                                              │
│    ⚠️  We do NOT store summaries - we fetch complete data!  │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 10. Fetch COMPLETE Guide Detail (Full Content)              │
│     GET /api/2.0/guides/12345                               │
│     Returns: COMPLETE guide data including:                 │
│       ✅ Introduction (full text)                           │
│       ✅ All Steps with:                                    │
│          - Step titles                                      │
│          - ALL instruction lines (every single line)         │
│          - ALL images (with all size URLs)                 │
│          - Tools, parts per step                            │
│       ✅ Conclusion (full text)                             │
│       ✅ Author info                                         │
│       ✅ Difficulty, time estimates                          │
│       ✅ Parts, tools, documents                            │
│                                                              │
│     ⚠️  This is the COMPLETE guide - nothing is skipped!    │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 11. Render COMPLETE Guide Content to Markdown              │
│     Function: _render_guide_content()                      │
│                                                              │
│     Input: Guide summary + COMPLETE detail                 │
│     Output: COMPLETE markdown string (all text, no limits) │
│                                                              │
│     ✅ Extracts EVERY line from EVERY step                  │
│     ✅ Includes ALL images (with all URL sizes)            │
│     ✅ Includes introduction AND conclusion                 │
│     ✅ No character limits - stores everything             │
│                                                              │
│     Format (COMPLETE content):                              │
│       # Guide Title                                         │
│                                                              │
│       Introduction text (complete, not truncated)...        │
│                                                              │
│       ## 1. Step 1 Title                                   │
│       - Step instruction line 1 (complete)                │
│       - Step instruction line 2 (complete)                  │
│       - Step instruction line 3 (complete)                  │
│       > **Note:** Note text (complete)                     │
│       > ⚠️ **Warning:** Warning text (complete)           │
│       > 💡 **Tip:** Tip text (complete)                    │
│       ![Step 1 Image 123](https://...original...)          │
│       <!-- Image URLs: thumbnail=..., medium=...,          │
│            large=..., original=... -->                      │
│                                                              │
│       ## 2. Step 2 Title                                   │
│       - All lines from step 2 (complete)                   │
│       ![Step 2 Image 124](https://...original...)            │
│       <!-- Image URLs: ... -->                              │
│       ... (ALL steps, ALL lines, ALL images)               │
│                                                              │
│       ## Conclusion                                         │
│       Conclusion text (complete, not truncated)...           │
│                                                              │
│     ⚠️  EVERYTHING is included - nothing is skipped!       │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 12. Extract Metadata                                        │
│     Build JSON object with:                                 │
│       - Guide ID, URL                                       │
│       - Step images (all sizes: thumbnail, medium, large,   │
│         original)                                           │
│       - Parts (with normalized URLs)                        │
│       - Documents (with download URLs)                      │
│       - Author info                                         │
│       - Difficulty, time estimates                          │
│       - Tools, prerequisites, flags                        │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 13. Store Guide in Database                                 │
│     Table: knowledge_sources                                │
│                                                              │
│     Generate UUID: uuid5(namespace, "ifixit/guide/12345")   │
│                                                              │
│     Fields:                                                 │
│       - id: UUID                                            │
│       - title: "iPhone 4 Screen Replacement"                │
│       - source_type: "ifixit"                               │
│       - raw_content: Full markdown text (unlimited length)  │
│       - model_id: UUID of EquipmentModel                   │
│       - word_count: Number of words in content              │
│       - metadata: JSON with all extracted metadata          │
└─────────────────────────────────────────────────────────────┘
```

### Phase 5: Progress Tracking

```
┌─────────────────────────────────────────────────────────────┐
│ 14. Update Progress Ledger                                  │
│     File: scripts/ifixit/state/ingest_state.csv            │
│                                                              │
│     After each device:                                      │
│       - Update category status                              │
│       - Record last device path                             │
│       - Record last guide ID                                │
│       - Increment counters                                  │
│       - Save to CSV                                         │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ 15. Write Checkpoint (Every N devices)                      │
│     File: scripts/ifixit/checkpoints/checkpoint_*.json      │
│                                                              │
│     Contains:                                                │
│       - Metrics (categories, devices, guides processed)      │
│       - Full ledger export                                  │
│       - Timestamp                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Where Data is Stored

### 1. **PostgreSQL Database**

#### Table: `equipment_families`
**Purpose**: Stores iFixit categories (e.g., "Phone", "Laptop")

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `id` | UUID | Deterministic UUID | `6a9a2400-...` |
| `name` | VARCHAR(255) | Category name | `"Phone"` |
| `description` | TEXT | Category description | `null` |
| `metadata` | JSONB | Category metadata | `{"ifixit": {...}}` |
| `created_at` | TIMESTAMP | Creation time | `2024-01-01 12:00:00` |

**Example Row:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Phone",
  "description": null,
  "metadata": {
    "ifixit": {
      "category_path": "Phone",
      "url": "https://www.ifixit.com/Category/Phone"
    }
  }
}
```

#### Table: `equipment_models`
**Purpose**: Stores iFixit devices (e.g., "iPhone 4", "MacBook Pro")

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `id` | UUID | Deterministic UUID | `...` |
| `family_id` | UUID | Foreign key to `equipment_families` | `...` |
| `manufacturer` | VARCHAR(255) | Manufacturer name | `"Apple"` |
| `model_name` | VARCHAR(255) | Model name | `"iPhone 4"` |
| `model_number` | VARCHAR(255) | Model number | `null` |
| `description` | TEXT | Device description | `null` |
| `image_urls` | JSONB | Device images | `null` |
| `metadata` | JSONB | Device metadata | `{"ifixit": {...}}` |
| `created_at` | TIMESTAMP | Creation time | `...` |

**Example Row:**
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440000",
  "family_id": "550e8400-e29b-41d4-a716-446655440000",
  "manufacturer": "Apple",
  "model_name": "iPhone 4",
  "metadata": {
    "ifixit": {
      "device_path": "Phone/iPhone/iPhone 4",
      "url": "https://www.ifixit.com/Device/iPhone+4"
    }
  }
}
```

#### Table: `knowledge_sources`
**Purpose**: Stores iFixit guides (repair manuals)

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `id` | UUID | Deterministic UUID | `...` |
| `title` | TEXT | Guide title | `"iPhone 4 Screen Replacement"` |
| `source_type` | VARCHAR(50) | Always `"ifixit"` | `"ifixit"` |
| `raw_content` | TEXT | **Full markdown content** (unlimited) | `"# Guide Title\n\n..."` |
| `model_id` | UUID | Foreign key to `equipment_models` | `...` |
| `word_count` | INT | Number of words | `1250` |
| `metadata` | JSONB | **Rich metadata** | `{"ifixit": {...}}` |
| `created_at` | TIMESTAMP | Creation time | `...` |
| `updated_at` | TIMESTAMP | Last update time | `...` |

**Example `raw_content` (COMPLETE text, no truncation):**
```markdown
# iPhone 4 Screen Replacement

This guide will help you replace a cracked screen. Follow these steps carefully to avoid damaging your device.

## 1. Remove the Home Button
- Use a spudger to pry up the home button.
- Be careful not to damage the ribbon cable underneath.
- The home button should pop out easily.
![Step 1 Image 12345](https://guide-images.cdn.ifixit.com/igi/abc123.full)
<!-- Image URLs: thumbnail=https://guide-images.cdn.ifixit.com/igi/abc123.thumbnail, medium=https://guide-images.cdn.ifixit.com/igi/abc123.medium, large=https://guide-images.cdn.ifixit.com/igi/abc123.large, original=https://guide-images.cdn.ifixit.com/igi/abc123.full -->

## 2. Remove the Display Assembly
- Disconnect the display cable connector.
- Use a plastic tool to carefully pry the connector.
- Lift the display assembly away from the device.
![Step 2 Image 12346](https://guide-images.cdn.ifixit.com/igi/def456.full)
<!-- Image URLs: thumbnail=https://..., medium=https://..., large=https://..., original=https://... -->

... (ALL steps, ALL lines, ALL images - COMPLETE content)
```

**Example `metadata`:**
```json
{
  "ifixit": {
    "guide_id": 12345,
    "url": "https://www.ifixit.com/Guide/iPhone+4+Screen+Replacement/12345",
    "step_images": [
      {
        "step_id": 1,
        "image_id": 12345,
        "urls": {
          "thumbnail": "https://guide-images.cdn.ifixit.com/igi/abc123.thumbnail",
          "medium": "https://guide-images.cdn.ifixit.com/igi/abc123.medium",
          "large": "https://guide-images.cdn.ifixit.com/igi/abc123.large",
          "original": "https://guide-images.cdn.ifixit.com/igi/abc123.full"
        }
      }
    ],
    "parts": [
      {
        "text": "iPhone 4 Screen",
        "url": "https://www.ifixit.com/Item/iPhone_4_Screen",
        "quantity": 1
      }
    ],
    "author": {
      "username": "iFixit",
      "url": "https://www.ifixit.com/User/1/iFixit"
    },
    "difficulty": "Moderate",
    "time_required": "30-60 minutes"
  }
}
```

### 2. **Progress Tracking Files**

#### File: `scripts/ifixit/state/ingest_state.csv`
**Purpose**: Tracks progress for resumability

**Format:**
```csv
category_path,status,last_device_path,last_device_index,last_guide_id,total_devices_processed,total_guides_processed,retry_count,failed_devices,last_error,updated_at
Phone,in_progress,Phone/iPhone/iPhone 4,5,12345,5,25,0,"[]",,2024-01-01T12:00:00
```

**Fields:**
- `category_path`: Category being processed (e.g., "Phone")
- `status`: `pending` | `in_progress` | `complete` | `failed`
- `last_device_path`: Last device processed
- `last_device_index`: Index of last device
- `last_guide_id`: Last guide ID processed
- `total_devices_processed`: Count of devices
- `total_guides_processed`: Count of guides
- `retry_count`: Number of retries
- `failed_devices`: JSON array of failed device paths
- `last_error`: Last error message
- `updated_at`: Timestamp

#### File: `scripts/ifixit/checkpoints/checkpoint_*.json`
**Purpose**: Periodic snapshots for recovery

**Format:**
```json
{
  "timestamp": "2024-01-01T12:00:00Z",
  "metrics": {
    "categories_processed": 1,
    "devices_processed": 50,
    "guides_processed": 250,
    "errors": []
  },
  "ledger": [
    {
      "category_path": "Phone",
      "status": "in_progress",
      "total_devices_processed": 50,
      "total_guides_processed": 250
    }
  ]
}
```

#### File: `scripts/ifixit/state/failed_devices.json`
**Purpose**: Quick reference for failed devices

**Format:**
```json
{
  "Phone": [
    {
      "device_path": "Phone/iPhone/iPhone 4",
      "error": "API timeout",
      "retry_count": 2
    }
  ]
}
```

---

## Progress Tracking & Resumability

### How Resumability Works

1. **Initial Run:**
   ```
   python -m scripts.ifixit.collect_ifixit_data
   ```
   - Creates `ingest_state.csv`
   - Processes categories → devices → guides
   - Updates CSV after each device
   - Writes checkpoints every 50 devices

2. **If Script Stops (Ctrl+C, crash, etc.):**
   - CSV file is saved with last position
   - Checkpoint JSON files contain snapshots

3. **Resume:**
   ```
   python -m scripts.ifixit.collect_ifixit_data --resume
   ```
   - Loads `ingest_state.csv`
   - Skips completed categories/devices
   - Continues from last position

4. **Retry Failed:**
   ```
   python -m scripts.ifixit.collect_ifixit_data --retry-failed
   ```
   - Loads failed devices from CSV
   - Retries only failed devices
   - Removes from failed list on success

---

## Database Schema & Relationships

```
equipment_families (Categories)
    │
    │ 1:N (one family has many models)
    │
    ▼
equipment_models (Devices)
    │
    │ 1:N (one model has many guides)
    │
    ▼
knowledge_sources (Guides)
    │
    │ 1:N (one guide has many chunks)
    │
    ▼
knowledge_chunks (For RAG/vector search)
```

**Relationships:**
- `EquipmentFamily` → `EquipmentModel` (one-to-many)
- `EquipmentModel` → `KnowledgeSource` (one-to-many)
- `KnowledgeSource` → `KnowledgeChunk` (one-to-many, for vector search)

**UUID Generation:**
- Uses **deterministic UUIDv5** (same input = same UUID)
- Namespace: `6a9a2400-8a73-4894-8dbf-2ecb8d8b9a6d`
- Family: `uuid5(namespace, f"ifixit/family/{category_path}")`
- Model: `uuid5(namespace, f"ifixit/model/{device_path}")`
- Guide: `uuid5(namespace, f"ifixit/guide/{guide_id}")`

**Why Deterministic UUIDs?**
- Safe to re-run (upserts instead of duplicates)
- Consistent IDs across runs
- Can reference by path/ID

---

## Complete Example Walkthrough

### Scenario: Extract "iPhone 4" guides

**Step 1: Start Collection**
```bash
python -m scripts.ifixit.collect_ifixit_data --category Phone --device-filter "iPhone 4"
```

**Step 2: API Calls Made**
```
1. GET /api/2.0/categories
   → Returns: {"Phone": {"iPhone": {"iPhone 4": null}}}

2. GET /api/2.0/guides?device=Phone/iPhone/iPhone%204
   → Returns: [{"guideid": 12345, "title": "Screen Replacement", ...}, ...]
   → ⚠️  These are ONLY summaries (just IDs and titles)
   → Purpose: To know which guides exist

3. GET /api/2.0/guides/12345
   → Returns: COMPLETE guide with:
      ✅ ALL steps (every single step)
      ✅ ALL lines from each step (every instruction line)
      ✅ ALL images (with all size URLs)
      ✅ Introduction (complete text)
      ✅ Conclusion (complete text)
      ✅ Parts, tools, documents, author info, etc.
   → ⚠️  This is the COMPLETE guide - nothing is skipped!
```

**Step 3: Database Writes**

**Write 1: Equipment Family**
```sql
INSERT INTO equipment_families (id, name, metadata)
VALUES (
  '550e8400-...',  -- UUID for "ifixit/family/Phone"
  'Phone',
  '{"ifixit": {"category_path": "Phone"}}'
)
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;
```

**Write 2: Equipment Model**
```sql
INSERT INTO equipment_models (id, family_id, manufacturer, model_name, metadata)
VALUES (
  '660e8400-...',  -- UUID for "ifixit/model/Phone/iPhone/iPhone 4"
  '550e8400-...',  -- Family UUID
  'Apple',
  'iPhone 4',
  '{"ifixit": {"device_path": "Phone/iPhone/iPhone 4"}}'
)
ON CONFLICT (id) DO UPDATE SET model_name = EXCLUDED.model_name;
```

**Write 3: Knowledge Source (Guide)**
```sql
INSERT INTO knowledge_sources (
  id, title, source_type, raw_content, model_id, word_count, metadata
)
VALUES (
  '770e8400-...',  -- UUID for "ifixit/guide/12345"
  'iPhone 4 Screen Replacement',
  'ifixit',
  '# iPhone 4 Screen Replacement\n\n...',  -- Full markdown
  '660e8400-...',  -- Model UUID
  1250,  -- Word count
  '{"ifixit": {"guide_id": 12345, "step_images": [...], ...}}'  -- JSON metadata
)
ON CONFLICT (id) DO UPDATE SET
  title = EXCLUDED.title,
  raw_content = EXCLUDED.raw_content,
  word_count = EXCLUDED.word_count,
  metadata = knowledge_sources.metadata || EXCLUDED.metadata;
```

**Step 4: Progress Update**
```csv
Phone,in_progress,Phone/iPhone/iPhone 4,0,12345,1,1,0,"[]",,2024-01-01T12:00:00
```

**Step 5: Checkpoint (after 50 devices)**
```json
{
  "timestamp": "2024-01-01T12:00:00Z",
  "metrics": {
    "categories_processed": 1,
    "devices_processed": 1,
    "guides_processed": 1
  }
}
```

---

## Key Points to Remember

1. **No Image Downloads**: Only URLs are stored, not binary image data
2. **Unlimited Content**: `raw_content` is TEXT type (no character limit)
3. **Complete Extraction**: All text, images (URLs), parts, tools, metadata
4. **Resumable**: Can stop and continue from last position
5. **Deterministic**: Same input always produces same UUID
6. **Concurrent**: Multiple devices processed in parallel
7. **Safe Upserts**: Re-running won't create duplicates

---

## Verification

To verify data is stored correctly:

```bash
# Check database
python -m scripts.ifixit.verify_extraction

# Show full content
python -m scripts.ifixit.show_full_content --limit 5

# Check completeness
python -m scripts.ifixit.check_content_completeness
```

---

## Summary

**Data Flow:**
```
iFixit API → Collector → PostgreSQL Database
                ↓
         Progress Files (CSV + JSON)
```

**Storage Locations:**
- **Database**: PostgreSQL (3 tables: families, models, knowledge_sources)
- **Progress**: CSV file (`state/ingest_state.csv`)
- **Checkpoints**: JSON files (`checkpoints/checkpoint_*.json`)
- **Failures**: JSON file (`state/failed_devices.json`)

**Content Stored (COMPLETE - Nothing Skipped):**
- ✅ **ALL text from ALL steps** (every single line, no truncation)
- ✅ **ALL image URLs** (in text as markdown + in metadata with all sizes)
- ✅ **Introduction and conclusion** (complete text)
- ✅ **All parts, tools, documents** (with URLs)
- ✅ **Author info, difficulty, time estimates**
- ✅ **Complete metadata** for future use
- ✅ **No character limits** - TEXT field stores unlimited content
- ✅ **No content is skipped** - everything from the API is extracted

