/**
 * OpenAI Embedding Service (Helper 2: generate_embeddings)
 *
 * This service generates embeddings for user prompts to enable semantic search.
 * It leverages OpenAI's embedding model to convert text into dense vectors,
 * which are then used for similarity-based knowledge chunk retrieval.
 *
 * Responsibilities:
 * - Generate embeddings using OpenAI Embeddings API
 * - Use text-embedding-3-small model for efficiency
 * - Handle text preprocessing (combining prompt + image descriptions)
 * - Return embedding vectors for RAG retrieval
 *
 * Team: Teammate 2
 * Your Helper Function: generate_embeddings(text)
 */

import { Injectable, Logger, BadRequestException } from '@nestjs/common';
import OpenAI from 'openai';

@Injectable()
export class OpenAIEmbeddingService {
  private readonly logger = new Logger(OpenAIEmbeddingService.name);
  private readonly openai: OpenAI;

  constructor() {
    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey) {
      throw new Error('OPENAI_API_KEY environment variable not configured');
    }
    this.openai = new OpenAI({ apiKey });
  }

  /**
   * Generate embedding for text input
   *
   * @param text - User prompt with appended image descriptions
   * @returns Embedding vector (1536 dimensions)
   *
   * Steps:
   * 1. Call OpenAI Embeddings API with text-embedding-3-small model
   * 2. Return embedding array
   */
  async generate(text: string): Promise<number[]> {
    if (!text || typeof text !== 'string') {
      throw new BadRequestException('Text is required for embedding generation');
    }

    const normalized = this.normalizeText(text);
    this.logger.debug(`Generating embedding (len=${normalized.length})`);

    // Retry up to 3 times for transient errors
    const maxRetries = 3;
    const baseDelay = 100;
    let lastError: any;
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const response = await this.openai.embeddings.create({
          model: 'text-embedding-3-small',
          input: normalized,
        });
        const embedding = response.data?.[0]?.embedding as number[] | undefined;
        if (!embedding || embedding.length === 0) {
          throw new Error('Empty embedding returned from OpenAI');
        }
        return embedding;
      } catch (error: any) {
        lastError = error;
        const status = error?.status ?? error?.response?.status;
        const isTransient = status === 429 || status === 500 || status === 503;
        if (isTransient && attempt < maxRetries) {
          const delay = Math.pow(2, attempt - 1) * baseDelay;
          this.logger.warn(`Embedding attempt ${attempt}/${maxRetries} failed (status=${status}). Retrying in ${delay}ms`);
          await new Promise((r) => setTimeout(r, delay));
          continue;
        }
        break;
      }
    }

    this.logger.error('Failed to generate embedding:', lastError);
    throw lastError;
  }

  /**
   * Helper: Call OpenAI Embeddings API
   */
  private async callOpenAIEmbeddings(text: string): Promise<any> {
    return this.openai.embeddings.create({
      model: 'text-embedding-3-small',
      input: text,
    });
  }

  /**
   * Helper: Extract embedding from API response
   */
  private extractEmbedding(response: any): number[] {
    const emb = response?.data?.[0]?.embedding as number[] | undefined;
    if (!emb || emb.length === 0) {
      throw new Error('OpenAI embedding response missing embedding array');
    }
    return emb;
  }

  private normalizeText(text: string): string {
    // Trim and collapse excessive whitespace
    return text.trim().replace(/\s+/g, ' ');
  }
}
