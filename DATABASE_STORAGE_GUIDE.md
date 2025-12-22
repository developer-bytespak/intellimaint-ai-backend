# Database Storage Implementation Guide

## Overview
Ab extraction k baad data ko **KnowledgeSource** table me automatically store hota hai. 

## KnowledgeSource Table Schema

```prisma
model KnowledgeSource {
  id         String           @id @default(uuid()) @db.Uuid
  title      String                            # Document name
  sourceType String           @map("source_type") @db.VarChar(50)  # "pdf", "html", "txt"
  rawContent String           @map("raw_content")  # Full extracted text
  modelId    String?          @map("model_id") @db.Uuid  # Optional: equipment model
  wordCount  Int?             @map("word_count")   # Auto-calculated
  metadata   Json?            # Custom metadata as JSON
  createdAt  DateTime         @default(now()) @map("created_at")
  updatedAt  DateTime         @updatedAt @map("updated_at")
  userId     String?          @map("user_id") @db.Uuid  # User who uploaded
  chunks     KnowledgeChunk[]  # Related chunks
  model      EquipmentModel?  @relation(fields: [modelId], references: [id])
  user       User?            @relation(fields: [userId], references: [id])
}

model KnowledgeChunk {
  id         String      @id @default(uuid()) @db.Uuid
  sourceId   String      @map("source_id") @db.Uuid  # Parent document
  chunkIndex Int         @map("chunk_index")         # Order in document
  content    String      # Chunk text (usually 250-500 tokens)
  heading    String?     # Optional heading for context
  embedding  Unsupported("vector")?  # For vector similarity search
  tokenCount Int?        @map("token_count")
  metadata   Json?
  createdAt  DateTime    @default(now()) @map("created_at")
  source     KnowledgeSource @relation(fields: [sourceId], references: [id], onDelete: Cascade)
}
```

## Flow Diagram

```
1. PDF Upload
   ↓
2. Background Extraction
   ├─ Text Extraction
   ├─ Table Extraction
   ├─ Image Upload to Supabase
   ├─ Unified Content Creation
   ↓
3. Database Storage (NEW!)
   ├─ Create KnowledgeSource record
   └─ (Optional) Create KnowledgeChunk records
   ↓
4. Completion Response
```

## API Endpoints

### 1. Upload & Extract PDF (with auto-DB storage)
```
POST /api/v1/extract/extract/full

Query Parameters:
- model_id (optional): Equipment model UUID
- user_id (optional): User UUID

Example:
POST /api/v1/extract/extract/full?user_id=abc-123&model_id=xyz-789
Content-Type: multipart/form-data

file: <pdf_file>
```

**Response:**
```json
{
  "job_id": "job-123",
  "status": "processing",
  "message": "PDF extraction started. Data will be stored in KnowledgeSource table.",
  "total_pages": 45
}
```

### 2. Check Progress
```
GET /api/v1/extract/extract/progress/{job_id}
```

**Response (on completion):**
```
Complete unified content as plain text
```

Or as JSON (at milestones):
```json
{
  "job_id": "job-123",
  "status": "processing",
  "progress": 75,
  "current_step": "database_storage",
  "message": "Storing in database..."
}
```

### 3. List All Knowledge Sources
```
GET /api/v1/extract/knowledge-sources

Optional Query:
- user_id: Filter by user
- model_id: Filter by equipment
- limit: 50 (default)
- offset: 0 (pagination)
```

**Response:**
```json
{
  "status": "success",
  "count": 5,
  "data": [
    {
      "id": "ks-123",
      "title": "Service Manual.pdf",
      "sourceType": "pdf",
      "wordCount": 5230,
      "createdAt": "2025-12-17T10:30:00Z",
      "metadata": {...}
    }
  ]
}
```

### 4. Get Specific Knowledge Source
```
GET /api/v1/extract/knowledge-sources/{source_id}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "id": "ks-123",
    "title": "Service Manual.pdf",
    "sourceType": "pdf",
    "rawContent": "Full extracted text content...",
    "wordCount": 5230,
    "modelId": "model-456",
    "userId": "user-789",
    "metadata": {
      "created_at": "2025-12-17T10:30:00Z",
      "word_count": 5230,
      "extraction_type": "automated"
    },
    "createdAt": "2025-12-17T10:30:00Z"
  }
}
```

### 5. Get Chunks for a Document
```
GET /api/v1/extract/knowledge-sources/{source_id}/chunks
```

**Response:**
```json
{
  "status": "success",
  "count": 25,
  "chunks": [
    {
      "id": "chunk-001",
      "sourceId": "ks-123",
      "chunkIndex": 0,
      "content": "This is the first chunk of content...",
      "heading": "Chapter 1: Introduction",
      "tokenCount": 250,
      "metadata": {}
    }
  ]
}
```

### 6. Delete Knowledge Source
```
DELETE /api/v1/extract/knowledge-sources/{source_id}
```

**Response:**
```json
{
  "status": "success",
  "message": "Knowledge source deleted successfully"
}
```

## Usage Examples

### Example 1: Upload PDF with User Context
```bash
curl -X POST "http://localhost:8000/api/v1/extract/extract/full?user_id=user-123&model_id=model-456" \
  -F "file=@service_manual.pdf"

# Response:
# {
#   "job_id": "job-xyz-123",
#   "status": "processing",
#   "message": "PDF extraction started..."
# }

# Check progress:
curl "http://localhost:8000/api/v1/extract/extract/progress/job-xyz-123"

# After completion, check stored data:
curl "http://localhost:8000/api/v1/extract/knowledge-sources?user_id=user-123"
```

### Example 2: Retrieve Stored Document
```python
import requests

# Get list of documents
response = requests.get("http://localhost:8000/api/v1/extract/knowledge-sources")
sources = response.json()["data"]

# Get specific document
source_id = sources[0]["id"]
response = requests.get(f"http://localhost:8000/api/v1/extract/knowledge-sources/{source_id}")
knowledge_source = response.json()["data"]

print(f"Title: {knowledge_source['title']}")
print(f"Word Count: {knowledge_source['wordCount']}")
print(f"Content Length: {len(knowledge_source['rawContent'])}")
```

### Example 3: Manual Storage (Direct Function Call)
```python
from app.services.knowledge_store_service import KnowledgeStoreService

# Store a document directly
result = KnowledgeStoreService.store_extracted_document(
    title="My Service Manual",
    full_content="Full extracted text content here...",
    source_type="pdf",
    model_id="model-123",
    user_id="user-456",
    chunked_content=[
        {
            "content": "Chunk 1 text...",
            "heading": "Section 1",
            "token_count": 250
        },
        {
            "content": "Chunk 2 text...",
            "heading": "Section 2",
            "token_count": 300
        }
    ]
)

print(result["knowledge_source"]["id"])  # Get the ID
```

## Key Functions in `KnowledgeStoreService`

### `create_knowledge_source()`
- Creates a single KnowledgeSource record
- Auto-calculates word count
- Returns UUID of created record

### `create_knowledge_chunks()`
- Creates multiple KnowledgeChunk records
- Maintains source_id relationship
- Preserves chunk order (chunkIndex)

### `store_extracted_document()`
- **Complete workflow** function
- Creates KnowledgeSource + chunks in one call
- Best for full document storage

### `get_knowledge_source()`
- Retrieve by ID with all metadata

### `list_knowledge_sources()`
- Filter by user_id or model_id
- Supports pagination

### `update_knowledge_source()`
- Update title, metadata, etc.
- Auto-updates timestamp

### `delete_knowledge_source()`
- Cascade deletes chunks automatically (Prisma handles)

## What Gets Stored

After extraction, here's what ends up in the database:

```
KnowledgeSource:
├─ Title: "service_manual.pdf"
├─ SourceType: "pdf"
├─ RawContent: "Full extracted text with images URLs and tables..."
├─ WordCount: 5230
├─ ModelId: "equipment-model-uuid" (if provided)
├─ UserId: "user-uuid" (if provided)
└─ Metadata:
   ├─ extraction_type: "automated"
   ├─ full_content_length: 185234 (characters)
   └─ created_at: "2025-12-17T10:30:00Z"

KnowledgeChunks (optional):
├─ Chunk 0: "Page 1-2 content..."
├─ Chunk 1: "Page 3-4 content..."
└─ ... (250-500 tokens per chunk)
```

## Database Schema Relationships

```
User (1) ──── (N) KnowledgeSource
              └──── (N) KnowledgeChunk

EquipmentModel (1) ──── (N) KnowledgeSource
                        └──── (N) KnowledgeChunk
```

## Error Handling

```python
result = KnowledgeStoreService.store_extracted_document(...)

if result["status"] == "success":
    source_id = result["knowledge_source"]["id"]
    print(f"Stored with ID: {source_id}")
else:
    print(f"Error: {result['error']}")
```

## Performance Notes

- **Word Count**: Auto-calculated from extracted text
- **Storage**: Entire content stored in rawContent field
- **Chunks**: Optional for vector search/RAG features
- **Metadata**: Flexible JSON field for custom data
- **Cascading**: Deleting KnowledgeSource auto-deletes chunks

## Next Steps

1. **Vector Embeddings**: Add embedding generation for chunks
2. **RAG Integration**: Use chunks for retrieval-augmented generation
3. **Search**: Implement full-text search on rawContent
4. **Analytics**: Track document processing metrics
5. **Versioning**: Store multiple versions of same document

