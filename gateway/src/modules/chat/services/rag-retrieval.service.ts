/**
 * RAG Retrieval Service (Helper 3: retrieve_relevant_chunks)
 *
 * This service performs semantic search on stored knowledge chunks using pgvector.
 * It queries the KnowledgeChunk table with the user's embedding to find the most
 * relevant documents for context injection into the LLM.
 *
 * Architecture:
 * - Uses pgvector's cosine distance operator (<=>)
 * - Leverages IVFFLAT index on knowledge_chunks.embedding for fast approximate search
 * - Returns chunks ordered by relevance (smallest distance = most similar)
 * - Validates 1536-dim embeddings and clamps K to safe bounds
 *
 * Pipeline Integration:
 * - Input: 1536-dim embedding array from OpenAIEmbeddingService
 * - Output: KnowledgeChunkData[] fed to ContextManagerService and then LLMService
 * - Stage 3 of ChatService.streamPipelineMessage()
 *
 * Performance:
 * - Target: <50ms for 43K+ rows with IVFFLAT index (lists=50)
 * - Without index: ~500ms+ (acceptable for small tables, not for production scale)
 *
 * Responsibilities:
 * - Execute pgvector similarity search with cosine distance
 * - Validate embedding dimension (1536) and format safely
 * - Clamp top-K to reasonable bounds (1–50)
 * - Filter NULL embeddings and return non-empty results
 * - Log metrics for observability
 * - Handle errors gracefully (non-critical failure in pipeline)
 */

import { Injectable, Logger, BadRequestException } from '@nestjs/common';
import { PrismaService } from 'prisma/prisma.service';
import { KnowledgeChunkData } from '../dto/pipeline-message.dto';

/**
 * Configuration constants for RAG retrieval
 * Easily tunable without code changes
 */
const TOP_K_DEFAULT = 10;
const MAX_TOP_K = 50;
const MIN_TOP_K = 1;
const EMBEDDING_DIMENSION = 1536;

/**
 * Similarity threshold for chunk filtering (cosine distance)
 * Lower values = stricter filtering (only very similar chunks)
 * Typical range: 0.3-0.5 for pgvector cosine distance (<=>)
 * Can be overridden via RAG_SIMILARITY_THRESHOLD env variable
 */
const DEFAULT_SIMILARITY_THRESHOLD = 0.4;

/**
 * Number of adjacent chunks to fetch before and after each retrieved chunk
 * This helps provide context when important information is split across chunks
 * (e.g., person's name in chunk 0, their CGPA in chunk 1)
 */
const ADJACENT_CHUNKS_COUNT: number = 1;

/**
 * Raw database row shape from knowledge_chunks query
 * Maps to KnowledgeChunkData DTO after retrieval
 */
interface KnowledgeChunkRow {
  id: string;
  content: string;
  heading: string | null;
  metadata: Record<string, unknown> | null;
  token_count: number | null;
  source_id: string;
  chunk_index: number;
}

@Injectable()
export class RagRetrievalService {
  private readonly logger = new Logger(RagRetrievalService.name);
  private readonly similarityThreshold: number;

  constructor(private prisma: PrismaService) {
    // Load similarity threshold from env or use default
    const envThreshold = process.env.RAG_SIMILARITY_THRESHOLD;
    this.similarityThreshold = envThreshold 
      ? parseFloat(envThreshold) 
      : DEFAULT_SIMILARITY_THRESHOLD;
    
    // Validate threshold is in reasonable range
    if (this.similarityThreshold < 0 || this.similarityThreshold > 2) {
      this.logger.warn(
        `⚠️ Invalid RAG_SIMILARITY_THRESHOLD=${envThreshold}, using default ${DEFAULT_SIMILARITY_THRESHOLD}`
      );
      this.similarityThreshold = DEFAULT_SIMILARITY_THRESHOLD;
    }
    
    this.logger.log(
      `✅ RAG similarity threshold: ${this.similarityThreshold} (cosine distance max)`
    );
  }

  /**
   * Retrieve top K most relevant knowledge chunks using pgvector cosine similarity
   *
   * Main entry point for RAG retrieval in the chat pipeline.
   *
   * @param embedding - Query embedding vector (must be 1536 dimensions)
   * @param topK - Number of chunks to retrieve (default 10, clamped to 1-50)
   * @param sourceId - Optional: filter by specific knowledge source ID
   * @returns Array of KnowledgeChunkData ordered by relevance (most similar first)
   * @throws BadRequestException if embedding dimension is invalid
   *
   * Process:
   * 1. Validate embedding dimension (exactly 1536)
   * 2. Clamp topK to safe bounds [1, MAX_TOP_K]
   * 3. Format embedding as PostgreSQL vector literal
   * 4. Execute pgvector similarity search with cosine distance (<=>)
   * 5. Map DB rows to KnowledgeChunkData DTO
   * 6. Log retrieval metrics
   * 7. Return chunks ordered by relevance
   *
   * Query approach:
   * - Uses IVFFLAT index on knowledge_chunks.embedding (vector_cosine_ops)
   * - Filters NULL embeddings (WHERE embedding IS NOT NULL)
   * - Orders by cosine distance ascending (smallest = most similar)
   * - Limits to clamped topK value
   * - Optional: filters by sourceId for scoped retrieval
   *
   * Expected query time: <50ms for 43K+ rows with IVFFLAT index
   */
  async retrieveTopK(
    embedding: number[],
    userId: string,
    topK?: number,
    sourceId?: string,
  ): Promise<KnowledgeChunkData[]> {
    const startTime = Date.now();

    try {
      // Validate embedding dimension
      this.validateEmbedding(embedding);

      // Clamp topK to safe bounds
      const clampedK = this.clampTopK(topK ?? TOP_K_DEFAULT);

      // Format embedding as PostgreSQL vector literal
      const vectorLiteral = this.formatVectorLiteral(embedding);

      this.logger.debug(
        `Retrieving top ${clampedK} chunks using pgvector cosine similarity`,
      );

      // Build and execute pgvector query
      const chunks = await this.executePgvectorQuery(
        vectorLiteral,
        clampedK,
        userId,
        sourceId,
      );

      // Fetch adjacent chunks to provide better context
      // This helps when important information is split across chunks
      // (e.g., person's name in chunk 0, their details in chunk 1)
      const chunksWithAdjacent = await this.fetchAdjacentChunks(chunks, userId);

      // Map DB rows to DTO
      const result: KnowledgeChunkData[] = chunksWithAdjacent.map((row: KnowledgeChunkRow) =>
        this.mapRowToDto(row),
      );

      // Log metrics
      const durationMs = Date.now() - startTime;
      this.logRetrievalMetrics(clampedK, result.length, durationMs, chunks.length);

      return result;
    } catch (error) {
      const durationMs = Date.now() - startTime;
      this.logger.error(
        `❌ RAG retrieval failed after ${durationMs}ms: ${error.message}`,
        error.stack,
      );
      throw error;
    }
  }

  /**
   * Fetch adjacent chunks (before and after) for each retrieved chunk
   * 
   * This ensures that when information is split across chunk boundaries
   * (like a person's name in one chunk and their details in the next),
   * the full context is available to the LLM.
   * 
   * @param chunks - Retrieved chunks from vector search
   * @param userId - User ID for access control
   * @returns Expanded array including adjacent chunks, deduplicated and sorted
   */
  private async fetchAdjacentChunks(
    chunks: KnowledgeChunkRow[],
    userId: string,
  ): Promise<KnowledgeChunkRow[]> {
    if (chunks.length === 0 || ADJACENT_CHUNKS_COUNT === 0) {
      return chunks;
    }

    // Build a set of (sourceId, chunkIndex) pairs to fetch
    const chunkKeysToFetch = new Set<string>();
    const existingChunkKeys = new Set<string>();

    // Track existing chunks and their adjacents
    for (const chunk of chunks) {
      const sourceId = chunk.source_id;
      const chunkIndex = chunk.chunk_index;
      
      existingChunkKeys.add(`${sourceId}:${chunkIndex}`);

      // Add adjacent chunk indices (before and after)
      for (let offset = -ADJACENT_CHUNKS_COUNT; offset <= ADJACENT_CHUNKS_COUNT; offset++) {
        if (offset === 0) continue; // Skip the current chunk
        const adjacentIndex = chunkIndex + offset;
        if (adjacentIndex >= 0) { // chunk_index can't be negative
          const key = `${sourceId}:${adjacentIndex}`;
          if (!existingChunkKeys.has(key)) {
            chunkKeysToFetch.add(key);
          }
        }
      }
    }

    // Remove keys that are already in our chunks
    for (const existingKey of existingChunkKeys) {
      chunkKeysToFetch.delete(existingKey);
    }

    if (chunkKeysToFetch.size === 0) {
      return chunks;
    }

    // Parse the keys into source/index pairs for the query
    const adjacentPairs: { sourceId: string; chunkIndex: number }[] = [];
    for (const key of chunkKeysToFetch) {
      const [sourceId, chunkIndexStr] = key.split(':');
      adjacentPairs.push({ sourceId, chunkIndex: parseInt(chunkIndexStr, 10) });
    }

    this.logger.debug(
      `Fetching ${adjacentPairs.length} adjacent chunks for context expansion`,
    );

    // Fetch adjacent chunks from database
    const adjacentChunks = await this.fetchChunksBySourceAndIndex(adjacentPairs, userId);

    // Combine original chunks with adjacent chunks
    const allChunks = [...chunks, ...adjacentChunks];

    // Deduplicate by id and sort by sourceId + chunkIndex for coherent ordering
    const uniqueChunksMap = new Map<string, KnowledgeChunkRow>();
    for (const chunk of allChunks) {
      if (!uniqueChunksMap.has(chunk.id)) {
        uniqueChunksMap.set(chunk.id, chunk);
      }
    }

    // Sort by source_id and chunk_index for logical ordering
    const sortedChunks = Array.from(uniqueChunksMap.values()).sort((a, b) => {
      if (a.source_id !== b.source_id) {
        return a.source_id.localeCompare(b.source_id);
      }
      return a.chunk_index - b.chunk_index;
    });

    return sortedChunks;
  }

  /**
   * Fetch specific chunks by their sourceId and chunkIndex
   * 
   * @param pairs - Array of {sourceId, chunkIndex} pairs to fetch
   * @param userId - User ID for access control
   * @returns Array of matching KnowledgeChunkRow objects
   */
  private async fetchChunksBySourceAndIndex(
    pairs: { sourceId: string; chunkIndex: number }[],
    userId: string,
  ): Promise<KnowledgeChunkRow[]> {
    if (pairs.length === 0) {
      return [];
    }

    // Build OR conditions for each (sourceId, chunkIndex) pair
    // Using a single query with multiple conditions is more efficient than N queries
    const conditions = pairs
      .map(p => `(kc.source_id = '${p.sourceId}'::uuid AND kc.chunk_index = ${p.chunkIndex})`)
      .join(' OR ');

    const query = `
      SELECT 
        kc.id, 
        kc.content, 
        kc.heading, 
        kc.metadata, 
        kc.token_count, 
        kc.source_id,
        kc.chunk_index
      FROM "knowledge_chunks" kc
      JOIN "knowledge_sources" ks ON kc.source_id = ks.id
      WHERE (${conditions})
        AND (ks.user_id IS NULL OR ks.user_id = '${userId}'::uuid)
    `;

    return this.prisma.$queryRawUnsafe<KnowledgeChunkRow[]>(query);
  }

  /**
   * Execute raw SQL pgvector query using Prisma $queryRaw
   *
   * Constructs and executes a SQL query that:
   * 1. Selects relevant chunk fields
   * 2. Filters out NULL embeddings
   * 3. Optionally filters by sourceId (for scoped retrieval)
   * 4. Orders by cosine distance (smallest first = most similar)
   * 5. Limits to K results
   *
   * The IVFFLAT index on embedding enables fast approximate search.
   * Cosine distance (<=> operator) matches embedding similarity.
   *
   * Note: Uses template literals with Prisma $queryRaw (not string concatenation)
   * to ensure proper parameterization and SQL type safety.
   *
   * @param vectorLiteral - PostgreSQL vector literal string (e.g., '[0.1,-0.2,...]')
   * @param topK - Number of results to return
   * @param sourceId - Optional filter for knowledge source
   * @returns Array of KnowledgeChunkRow objects
   */
  private async executePgvectorQuery(
    vectorLiteral: string,
    topK: number,
    userId: string,
    sourceId?: string,
  ): Promise<KnowledgeChunkRow[]> {
    // Scoped retrieval: filter by sourceId
    if (sourceId) {
      return this.prisma.$queryRaw`
        SELECT 
          kc.id, 
          kc.content, 
          kc.heading, 
          kc.metadata, 
          kc.token_count, 
          kc.source_id,
          kc.chunk_index
        FROM "knowledge_chunks" kc
        JOIN "knowledge_sources" ks ON kc.source_id = ks.id
        WHERE kc.embedding IS NOT NULL 
          AND kc.source_id = ${sourceId}::uuid
          AND (ks.user_id IS NULL OR ks.user_id = ${userId}::uuid)
        ORDER BY kc.embedding <=> ${vectorLiteral}::vector ASC
        LIMIT ${topK}
      `;
    }

    // Unscoped retrieval: all knowledge chunks ordered by relevance
    return this.prisma.$queryRaw`
      SELECT 
        kc.id, 
        kc.content, 
        kc.heading, 
        kc.metadata, 
        kc.token_count, 
        kc.source_id,
        kc.chunk_index
      FROM "knowledge_chunks" kc
      JOIN "knowledge_sources" ks ON kc.source_id = ks.id
      WHERE kc.embedding IS NOT NULL
        AND (ks.user_id IS NULL OR ks.user_id = ${userId}::uuid)
        AND kc.embedding <=> ${vectorLiteral}::vector < ${this.similarityThreshold}
      ORDER BY kc.embedding <=> ${vectorLiteral}::vector ASC
      LIMIT ${topK}
    `;
  }

  /**
   * Convert number[] embedding to PostgreSQL vector literal string
   *
   * PostgreSQL requires vector literals in format: '[val1, val2, ...]'
   * This method safely converts a float array to that format.
   *
   * @param embedding - Array of numbers (1536 elements expected)
   * @returns String in format '[0.12,-0.34,...]' safe for SQL
   *
   * Steps:
   * 1. Join numbers with commas (no spaces for safety)
   * 2. Wrap in square brackets for vector notation
   * 3. Return as string that Prisma will cast to ::vector
   *
   * Example:
   * Input:  [0.123, -0.456, 0.789, ...]
   * Output: "[0.123,-0.456,0.789,...]"
   */
  private formatVectorLiteral(embedding: number[]): string {
    // Join array elements as comma-separated values, no spaces
    const vectorElements = embedding
      .map((val) => {
        // Handle edge cases: NaN, Infinity
        if (!isFinite(val)) {
          this.logger.warn(
            `⚠️ Non-finite value in embedding: ${val}, replacing with 0`,
          );
          return '0';
        }
        return val.toString();
      })
      .join(',');

    // Return as PostgreSQL vector literal: [val1,val2,...]
    // No quotes - Prisma template literal will handle the casting
    return `[${vectorElements}]`;
  }

  /**
   * Validate embedding dimension and type
   *
   * Type guard: ensures embedding is a valid array of numbers with correct dimension.
   * Throws BadRequestException if validation fails.
   *
   * @param embedding - Unknown input to validate
   * @throws BadRequestException if not array, wrong dimension, or contains non-numbers
   */
  private validateEmbedding(embedding: unknown): void {
    if (!Array.isArray(embedding)) {
      throw new BadRequestException(
        `Embedding must be an array, got ${typeof embedding}`,
      );
    }

    if (embedding.length !== EMBEDDING_DIMENSION) {
      throw new BadRequestException(
        `Embedding must have ${EMBEDDING_DIMENSION} dimensions, got ${embedding.length}`,
      );
    }

    if (!embedding.every((val) => typeof val === 'number')) {
      throw new BadRequestException(
        `Embedding must contain only numbers; found non-numeric value`,
      );
    }

    // Optional: check for extreme values that might indicate encoding error
    const hasNonFinite = embedding.some((val) => !isFinite(val));
    if (hasNonFinite) {
      this.logger.warn(
        `⚠️ Embedding contains non-finite values (NaN/Infinity); query may fail`,
      );
    }
  }

  /**
   * Clamp top-K value to safe bounds
   *
   * Prevents abuse and ensures reasonable token/context budgets.
   * Min: 1 (at least one result)
   * Max: 50 (default max, tunable)
   * Default: 10 (good balance for most use cases)
   *
   * @param topK - User-requested number of chunks
   * @returns Clamped value in range [MIN_TOP_K, MAX_TOP_K]
   */
  private clampTopK(topK: number): number {
    const clamped = Math.max(MIN_TOP_K, Math.min(topK, MAX_TOP_K));

    if (clamped !== topK) {
      this.logger.debug(
        `⚠️ Clamped topK from ${topK} to ${clamped} (bounds: ${MIN_TOP_K}–${MAX_TOP_K})`,
      );
    }

    return clamped;
  }

  /**
   * Map database row to KnowledgeChunkData DTO
   *
   * Converts raw Prisma query result to typed DTO for downstream consumption.
   * Ensures all fields are properly formatted and null-safe.
   *
   * @param row - Raw knowledge_chunks table row
   * @returns Typed KnowledgeChunkData object
   */
  private mapRowToDto(row: KnowledgeChunkRow): KnowledgeChunkData {
    return {
      id: row.id,
      content: row.content,
      heading: row.heading || undefined,
      metadata: row.metadata || undefined,
      tokenCount: row.token_count || undefined,
      sourceId: row.source_id,
      chunkIndex: row.chunk_index,
    };
  }

  /**
   * Log retrieval performance metrics
   *
   * Emits structured logs for observability and performance monitoring.
   * Useful for detecting slow queries, index effectiveness, etc.
   *
   * @param topKRequested - Original K value requested (before clamping)
   * @param resultCount - Actual number of chunks returned (including adjacent)
   * @param durationMs - Query execution time in milliseconds
   * @param originalCount - Number of chunks from vector search (before adjacent expansion)
   *
   * Logs format: "✅ Retrieved N/K chunks (M with adjacents) in Xms"
   */
  private logRetrievalMetrics(
    topKRequested: number,
    resultCount: number,
    durationMs: number,
    originalCount?: number,
  ): void {
    const adjacentInfo = originalCount !== undefined && originalCount !== resultCount
      ? ` (${originalCount} matched + ${resultCount - originalCount} adjacent)`
      : '';

    // Warn about no chunks passing threshold
    if (resultCount === 0) {
      this.logger.warn(
        `⚠️ No chunks passed similarity threshold (${this.similarityThreshold}) in ${durationMs}ms – query may be too generic or threshold too strict`,
      );
      return;
    }

    if (durationMs > 100) {
      this.logger.warn(
        `⚠️ Slow retrieval: ${resultCount}/${topKRequested} chunks${adjacentInfo} in ${durationMs}ms (threshold=${this.similarityThreshold}) – consider index reanalysis`,
      );
    } else {
      this.logger.debug(
        `✅ Retrieved ${resultCount}/${topKRequested} chunks${adjacentInfo} in ${durationMs}ms (threshold=${this.similarityThreshold})`,
      );
    }
  }
}
