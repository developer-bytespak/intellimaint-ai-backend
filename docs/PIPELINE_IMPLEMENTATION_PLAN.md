# RAG Chat Pipeline Implementation Plan

## Overview

This document outlines the implementation plan for the core chat pipeline API - the most crucial component of IntelliMaint. This API handles the complete flow from user prompt submission to structured response generation, incorporating image analysis, embedding-based retrieval, and context-aware LLM interactions.

---

## Architecture Overview

### High-Level Flow

```
User (Frontend)
    ↓
Socket.IO Event: 'stream-pipeline-message'
    ↓
SocketChatGateway (Entry Point)
    ↓
ChatService.streamPipelineMessage() (Orchestrator)
    ├─ Stage 1: Process Images → OpenAIVisionService
    ├─ Stage 2: Generate Embeddings → OpenAIEmbeddingService
    ├─ Stage 3: Retrieve Knowledge → RagRetrievalService
    ├─ Stage 4: Prepare Context → ContextManagerService
    ├─ Stage 5: Stream LLM Response → OpenAILLMService
    ├─ Stage 6: Store Response → ChatService (DB)
    ├─ Stage 7: Update Context Summary → ContextManagerService
    ↓
Stream Response Back to Frontend via Socket.IO
```

---

## File Structure

```
gateway/src/modules/chat/
├── controllers/
│   └── chat.controller.ts                    (Existing - REST endpoints)
├── gateway/
│   └── socket-chat.gateway.ts                (Existing - Socket.IO entry point)
├── services/
│   ├── chat.service.ts                       (EXISTING - Core orchestrator)
│   ├── openai-vision.service.ts              (NEW - Helper 1)
│   ├── openai-embedding.service.ts           (NEW - Helper 2)
│   ├── rag-retrieval.service.ts              (NEW - Helper 3)
│   ├── context-manager.service.ts            (NEW - Helper 4 + 7)
│   └── openai-llm.service.ts                 (NEW - Helper 5)
├── dto/
│   ├── create-message.dto.ts                 (Existing)
│   └── pipeline-message.dto.ts               (NEW - Pipeline-specific)
└── chat.module.ts                            (Existing - Updated with new providers)
```

---

## File Responsibilities & Team Assignment

### 1. SocketChatGateway (Entry Point)
**File**: `gateway/socket-chat.gateway.ts`  
**Status**: Update existing file  
**Responsibility**: 
- Listen for `stream-pipeline-message` Socket.IO event from frontend
- Extract authenticated user from JWT
- Delegate to `ChatService.streamPipelineMessage()`
- Stream chunks back to frontend via `pipeline-chunk` event
- Handle errors and emit `pipeline-error` events

**Input from Frontend**:
```typescript
{
  sessionId: string;
  content: string;           // User prompt
  images?: string[];         // Up to 5 images (URLs or base64)
}
```

**Output to Frontend** (streamed chunks):
```typescript
{
  stage: 'image-analysis' | 'embedding' | 'retrieval' | 'context' | 'llm-generation' | 'complete';
  token?: string;            // Only for 'llm-generation' stage
  metadata?: {
    analyses?: ImageAnalysisResult[];
    chunkCount?: number;
    retrievedChunks?: KnowledgeChunk[];
    imageDescriptions?: string;
  };
  messageId?: string;        // Only in 'complete' stage
  done?: boolean;
}
```

---

### 2. ChatService (Main Orchestrator) ⭐ MAIN RESPONSIBILITY
**File**: `gateway/src/modules/chat/services/chat.service.ts`  
**Status**: Add new method to existing file  
**Team**: You  
**Responsibility**:
- **Orchestrate the entire pipeline** by calling helper services sequentially
- **Store user message** in database with attachments
- **Coordinate all pipeline stages** and yield updates
- **Store assistant response** after LLM completion
- **Handle errors gracefully** (partial failures on non-critical stages)
- **Manage database transactions** for data consistency

**Methods to Implement**:

#### Main Orchestrator
```typescript
async *streamPipelineMessage(
  userId: string, 
  sessionId: string, 
  dto: PipelineMessageDto
): AsyncGenerator<PipelineChunk>
```
- Calls all helpers in sequence
- Yields chunk updates at each stage
- Handles failures gracefully

#### Database Operations
```typescript
private async storeUserMessage(
  userId: string, 
  sessionId: string, 
  dto: PipelineMessageDto
): Promise<ChatMessage>
```
- Create ChatMessage record (role: 'user')
- Create MessageAttachment records if images present

```typescript
private async fetchSessionHistory(
  sessionId: string
): Promise<ChatMessage[]>
```
- Get all messages for session ordered by creation time

```typescript
private async storeAssistantMessage(
  sessionId: string, 
  content: string, 
  tokenUsage: TokenUsage
): Promise<ChatMessage>
```
- Create ChatMessage record (role: 'assistant')
- Store token usage for billing

---

### 3. OpenAI Vision Service (Helper 1: process_images)
**File**: `gateway/src/modules/chat/services/openai-vision.service.ts`  
**Status**: NEW  
**Team**: **Teammate 1**  
**Your Helper Function**: `process_images(prompt, images)`

**Responsibility**:
- Analyze each attached image using OpenAI Vision API
- Store analysis results in `ImageAnalysis` table
- Store image metadata in `MessageAttachment` table
- Return image descriptions to be appended to prompt

**Methods to Implement**:

```typescript
async analyzeAndStoreImages(
  messageId: string, 
  images: string[]
): Promise<ImageAnalysisResult[]>
```
- For each image:
  - Call OpenAI Vision API (`gpt-4o` with vision)
  - Extract: `sceneDescription`, `detectedComponents`, `ocrResults`
  - Store in `ImageAnalysis` table (via Prisma)
  - Create `MessageAttachment` record linking image to message
- Return array of results with descriptions

**Inputs**:
- `messageId`: FK to ChatMessage (for storing attachments)
- `images[]`: Array of image URLs or base64 strings

**Outputs**:
```typescript
{
  attachmentId: string;
  description: string;           // Generated by Vision API
  detectedComponents?: object;   // Detection results
  ocrResults?: string;          // Text extracted from image
}[]
```

**External Dependencies**:
- OpenAI API (Vision capability)

**Database Tables**:
- `ImageAnalysis` (insert)
- `MessageAttachment` (insert)

---

### 4. OpenAI Embedding Service (Helper 2: generate_embeddings)
**File**: `gateway/src/modules/chat/services/openai-embedding.service.ts`  
**Status**: NEW  
**Team**: **Teammate 2**  
**Your Helper Function**: `generate_embeddings(text)`

**Responsibility**:
- Generate embeddings for user prompt (with appended image descriptions)
- Use OpenAI Embeddings API (text-embedding-3-small model)
- Return vector for similarity search

**Methods to Implement**:

```typescript
async generate(text: string): Promise<number[]>
```
- Call OpenAI Embeddings API with model `text-embedding-3-small`
- Return the embedding vector (1536 dimensions)

**Inputs**:
- `text`: User prompt + image descriptions combined

**Outputs**:
- `number[]`: Embedding vector (1536 values)

**External Dependencies**:
- OpenAI API (Embeddings endpoint)

**Database Tables**:
- None (embeddings passed to retrieval service)

---

### 5. RAG Retrieval Service (Helper 3: retrieve_relevant_chunks)
**File**: `gateway/src/modules/chat/services/rag-retrieval.service.ts`  
**Status**: NEW  
**Team**: **Teammate 3**  
**Your Helper Function**: `retrieve_relevant_chunks(query_embedding, max_results=10)`

**Responsibility**:
- Query `KnowledgeChunk` table using pgvector similarity search
- Use cosine similarity with generated embedding
- Return top N (default 10) most relevant chunks
- Include chunk content, metadata, and source information

**Methods to Implement**:

```typescript
async retrieveTopK(
  embedding: number[], 
  topK: number = 10
): Promise<KnowledgeChunk[]>
```
- Execute Prisma `$queryRaw` with pgvector `<=>` operator (cosine distance)
- Order results by similarity (ascending distance)
- Limit to `topK` results
- Return full KnowledgeChunk objects

**Inputs**:
- `embedding[]`: Float array (1536 dimensions from embedding service)
- `topK`: Number of chunks to retrieve (default 10)

**Outputs**:
```typescript
{
  id: string;
  content: string;          // Raw chunk text
  heading?: string;         // Section heading
  metadata?: object;        // Source metadata
  tokenCount?: number;      // For cost tracking
  sourceId: string;         // Reference to source document
}[]
```

**External Dependencies**:
- PostgreSQL pgvector extension (already set up)

**Database Tables**:
- `KnowledgeChunk` (read-only, similarity search)

---

### 6. Context Manager Service (Helper 4 + 7: generate_context_summary + update_context_summary)
**File**: `gateway/src/modules/chat/services/context-manager.service.ts`  
**Status**: NEW  
**Team**: **Teammate 4**  
**Your Helper Functions**: 
- `generate_context_summary(prompts_and_responses)` (Helper 4)
- `update_context_summary(new_summary)` (Helper 7)

**Responsibility**:
- Manage conversation context window (5-message sliding window)
- Generate summaries for older messages using LLM
- Prepare context data for LLM calls
- Incrementally update stored summaries after each turn

**Context Window Logic**:
- **First 5 messages**: Pass all messages as-is to LLM
- **After 5 messages**: Keep last 5 messages + summary of older ones
- **Summary Update**: Generate new summary every 5 messages

**Methods to Implement**:

```typescript
async prepareContext(
  sessionId: string, 
  messages: ChatMessage[]
): Promise<{
  summary: string;
  recentMessages: ChatMessage[];
}>
```
- If `messages.length <= 5`: Return all messages, empty summary
- If `messages.length > 5`:
  - Get existing summary from `ChatSession.contextSummary`
  - Get last 5 messages
  - Return both

```typescript
async updateContextSummary(
  sessionId: string, 
  userMessage: ChatMessage, 
  assistantMessage: ChatMessage
): Promise<void>
```
- Fetch current message count for session
- If total messages is multiple of 5:
  - Get all older messages (not in last 5)
  - Generate new summary using OpenAI API
  - Update `ChatSession.contextSummary` in database

```typescript
private async generateSummary(messages: ChatMessage[]): Promise<string>
```
- Call OpenAI API to summarize conversation
- Return concise summary of main points

**Inputs**:
- `sessionId`: Chat session identifier
- `messages`: Array of ChatMessage objects
- `userMessage`, `assistantMessage`: Latest interaction

**Outputs**:
- `{ summary: string, recentMessages: ChatMessage[] }`

**External Dependencies**:
- OpenAI API (for summarization)

**Database Tables**:
- `ChatSession` (read/update `contextSummary`)
- `ChatMessage` (read)

---

### 7. OpenAI LLM Service (Helper 5: final_llm_call)
**File**: `gateway/src/modules/chat/services/openai-llm.service.ts`  
**Status**: NEW  
**Team**: **Teammate 5**  
**Your Helper Function**: `final_llm_call(user_prompt, context_summary, relevant_chunks, images)`

**Responsibility**:
- Build comprehensive system and user messages
- Include retrieved knowledge chunks as context
- Include conversation context summary
- Stream response from OpenAI Chat API (gpt-4o)
- Yield tokens one by one for frontend display

**Methods to Implement**:

```typescript
async *streamCompletion(
  userPrompt: string,
  contextSummary: string,
  chunks: KnowledgeChunk[],
  images: string[]
): AsyncGenerator<string>
```
- Build system prompt with:
  - Role instructions
  - Context summary (if exists)
  - Knowledge chunks formatted as reference material
- Build user message with:
  - User prompt text
  - Attached images
- Open streaming connection to OpenAI `gpt-4o`
- Yield each token as received

```typescript
private buildSystemPrompt(
  contextSummary: string, 
  chunks: KnowledgeChunk[]
): string
```
- Format system instructions
- Include knowledge chunks as context
- Add fallback logic (when to use own knowledge vs chunks)

**Inputs**:
- `userPrompt`: Original user question
- `contextSummary`: Summary of previous conversation
- `chunks[]`: Top 10 relevant knowledge chunks
- `images[]`: Attached images (URLs)

**Outputs**:
- Async generator yielding text tokens one by one

**External Dependencies**:
- OpenAI API (Chat Completions with streaming)

**Database Tables**:
- None (orchestrator handles storage)

---

### 8. Pipeline Message DTO
**File**: `gateway/src/modules/chat/dto/pipeline-message.dto.ts`  
**Status**: NEW  
**Responsibility**:
- Define request/response types for pipeline API
- Validation decorators for inputs
- Type definitions for internal communication

**Classes to Define**:
- `PipelineMessageDto` (request from frontend)
- `PipelineChunk` (response chunk)
- `ImageAnalysisResult`
- `TokenUsage`

---

### 9. Chat Module
**File**: `gateway/src/modules/chat/chat.module.ts`  
**Status**: Update existing file  
**Responsibility**:
- Register all new services in module providers
- Export services for dependency injection

**Add to providers**:
- `OpenAIVisionService`
- `OpenAIEmbeddingService`
- `RagRetrievalService`
- `ContextManagerService`
- `OpenAILLMService`

---

## Pipeline Execution Flow

### Step-by-Step Execution

1. **User submits prompt via Socket.IO**
   ```
   Frontend → SocketChatGateway (event: 'stream-pipeline-message')
   ```

2. **Gateway authenticates and delegates**
   ```
   SocketChatGateway → ChatService.streamPipelineMessage()
   ```

3. **Stage 1: Store User Message**
   ```
   ChatService.storeUserMessage()
   → Creates ChatMessage (role: 'user')
   → Creates MessageAttachment records if images exist
   ```

4. **Stage 2: Analyze Images** (if images present)
   ```
   OpenAIVisionService.analyzeAndStoreImages()
   → Calls OpenAI Vision API
   → Stores ImageAnalysis records
   → Returns image descriptions
   ← Yield: { stage: 'image-analysis', analyses: [...] }
   ```

5. **Stage 3: Generate Embeddings**
   ```
   OpenAIEmbeddingService.generate()
   → Combines prompt + image descriptions
   → Calls OpenAI Embeddings API
   → Returns vector
   ← Yield: { stage: 'embedding' }
   ```

6. **Stage 4: Retrieve Knowledge Chunks**
   ```
   RagRetrievalService.retrieveTopK()
   → Queries pgvector similarity search
   → Returns top 10 chunks
   ← Yield: { stage: 'retrieval', chunkCount: 10 }
   ```

7. **Stage 5: Prepare Context**
   ```
   ContextManagerService.prepareContext()
   → Fetches session history
   → Gets/generates summary if needed
   → Returns context data
   ```

8. **Stage 6: Stream LLM Response**
   ```
   OpenAILLMService.streamCompletion()
   → Builds system + user messages
   → Opens stream to OpenAI gpt-4o
   → Yields tokens
   ← Yield: { stage: 'llm-generation', token: '...' } (per token)
   ```

9. **Stage 7: Store Assistant Message**
   ```
   ChatService.storeAssistantMessage()
   → Creates ChatMessage (role: 'assistant')
   → Stores full response text
   → Records token usage
   ```

10. **Stage 8: Update Context Summary**
    ```
    ContextManagerService.updateContextSummary()
    → Checks if summary needs update (every 5 messages)
    → Generates new summary if needed
    → Updates ChatSession.contextSummary
    ← Yield: { stage: 'complete', messageId: '...' }
    ```

11. **Stream complete**
    ```
    Frontend receives all chunks and displays response
    ```

---

## Error Handling Strategy

### Non-Critical Failures (Continue Pipeline)
- **Image analysis fails**: Continue without image descriptions
- **Embedding generation fails**: ❌ ABORT (can't retrieve without it)

### Critical Failures (Abort Pipeline)
- **Authentication fails**: Return 401 Unauthorized
- **Session not found**: Return 404 Not Found
- **Database error**: Return 500 Internal Server Error

### Error Recovery
- Log all failures with stage context
- Send error event to frontend via Socket.IO
- Clean up partial data if transaction fails

---

## Performance Considerations

### Parallel Processing Opportunities
```typescript
// Process multiple images in parallel
const imageAnalyses = await Promise.all(
  images.map(img => this.openaiVisionService.analyze(img))
);
```

### Caching Strategies (Future)
- Cache image analysis results by file hash
- Cache embeddings for repeated queries
- Use OpenAI context caching for conversation history

### Token Usage Tracking
- Track token usage per stage
- Store in database for billing
- Monitor for cost optimization

---

## Development Workflow

### Phase 1: Setup (You)
1. Create all service file stubs with interfaces
2. Update `chat.module.ts` with providers
3. Add `streamPipelineMessage()` skeleton to `ChatService`

### Phase 2: Helper Implementation (Team)
Each teammate implements their assigned helper service:
- **Teammate 1**: `OpenAIVisionService` (Helper 1)
- **Teammate 2**: `OpenAIEmbeddingService` (Helper 2)
- **Teammate 3**: `RagRetrievalService` (Helper 3)
- **Teammate 4**: `ContextManagerService` (Helper 4 + 7)
- **Teammate 5**: `OpenAILLMService` (Helper 5)

**Each teammate should**:
- Implement interface methods
- Add comprehensive JSDoc comments
- Write unit tests
- Ensure error handling

### Phase 3: Integration (You)
1. Complete `streamPipelineMessage()` orchestrator
2. Update `SocketChatGateway` to call orchestrator
3. Integration testing
4. Connect frontend

### Phase 4: Testing
- Unit tests for each service
- Integration tests for full pipeline
- E2E tests with frontend

---

## Environment Variables Required

```env
# OpenAI
OPENAI_API_KEY=sk-...

# Database
DATABASE_URL=postgresql://...

# Gateway
GATEWAY_PORT=3000
JWT_SECRET=...
FRONTEND_URL=http://localhost:3001
```

---

## Success Criteria

- ✅ Each helper service independently callable and testable
- ✅ Full pipeline executes without errors
- ✅ Images analyzed and stored correctly
- ✅ Embeddings generated for retrieval
- ✅ Top 10 chunks retrieved via pgvector
- ✅ Context summary generated/updated correctly
- ✅ LLM response streamed with context awareness
- ✅ All data persisted to database
- ✅ Frontend receives streamed response

---

## References

- Original Pipeline Plan: [prompt-response-pipeline.md](./prompt-response-pipeline.md)
- Prisma Schema: [schema.prisma](../../schema.prisma)
- Chat Module Structure: [gateway/src/modules/chat/](../../src/modules/chat/)
