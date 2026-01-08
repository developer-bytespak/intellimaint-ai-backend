/**
 * OpenAI LLM Service (Helper 5: final_llm_call)
 *
 * This service handles streaming chat completions from OpenAI's API.
 * It constructs comprehensive prompts including user input, retrieved knowledge,
 * conversation context, and images, then streams responses back token by token.
 *
 * Responsibilities:
 * - Build system prompt with RAG context and instructions
 * - Build user message with text and images
 * - Stream responses from OpenAI gpt-4o model
 * - Yield tokens one by one for frontend display
 * - Handle streaming errors and cleanup
 *
 * Team: Teammate 5
 * Your Helper Function: final_llm_call(user_prompt, context_summary, relevant_chunks, images)
 */

import { Injectable, Logger } from '@nestjs/common';
import OpenAI from 'openai';
import { KnowledgeChunkData } from '../dto/pipeline-message.dto';

@Injectable()
export class OpenAILLMService {
  private readonly logger = new Logger(OpenAILLMService.name);
  private readonly openai: OpenAI;
  private readonly MODEL_ID = 'gpt-4o';
  private readonly MAX_TOKENS = 2048;
  private readonly TEMPERATURE = 0.7;

  constructor() {
    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey) {
      throw new Error('OPENAI_API_KEY environment variable not configured');
    }
    this.openai = new OpenAI({ apiKey });
  }

  /**
   * Stream chat completion from OpenAI with context awareness
   *
   * @param userPrompt - Original user question (without image descriptions)
   * @param contextSummary - Summary of previous conversation (if any)
   * @param chunks - Top 10 relevant knowledge chunks for context
   * @param images - Array of image URLs to include in message
   * @returns Async generator yielding response tokens
   *
   * Steps:
   * 1. Build system prompt with role, context, and knowledge chunks
   * 2. Build user message with prompt text and images
   * 3. Open streaming connection to OpenAI gpt-4o
   * 4. Yield each token as received from API
   * 5. Handle errors gracefully
   */
  async *streamCompletion(
    userPrompt: string,
    contextSummary: string,
    chunks: KnowledgeChunkData[],
    images: string[],
  ): AsyncGenerator<string> {
    this.logger.debug(
      `Starting LLM stream with ${chunks.length} chunks and ${images.length} images`,
    );

    // Build prompts
    const systemPrompt = this.buildSystemPrompt(contextSummary, chunks);
    const userMessage = this.buildUserMessage(userPrompt, images);

    // Call OpenAI streaming API and yield tokens
    try {
      for await (const token of this.callOpenAIStream(systemPrompt, userMessage)) {
        if (token) {
          yield token;
        }
      }
    } catch (error: any) {
      this.logger.error(`OpenAI stream error: ${error.message}`, error.stack);
      throw error;
    }
  }

  /**
   * Helper: Build system prompt with context and instructions
   *
   * Includes:
   * - Role definition (helpful AI assistant)
   * - Context summary if conversation history exists
   * - Retrieved knowledge chunks formatted for reference
   * - Fallback instructions (when to use knowledge vs. own knowledge)
   */
  private buildSystemPrompt(contextSummary: string, chunks: KnowledgeChunkData[]): string {
    this.logger.debug(`Building system prompt with ${chunks.length} chunks`);
    const lines: string[] = [];

    // Role and interaction policy: user-focused, no backend/source disclosure
    lines.push(
      'You are IntelliMaint, a helpful maintenance assistant. Answer clearly and concisely. '
      + 'Do not mention internal systems, databases, or sources. '
      + 'If provided context includes relevant information, use it to ground your answer. '
      + 'If information is insufficient, respond naturally using your knowledge, or ask clarifying questions. '
      + 'Do not invent part numbers/specs; ask for more details when uncertain.'
    );

    // Include brief conversation summary when available
    if (contextSummary && contextSummary.trim().length > 0) {
      lines.push('\nConversation summary (for context):');
      lines.push(contextSummary.trim());
    }

    // Knowledge chunks formatted for internal grounding (not shown to user)
    if (chunks && chunks.length > 0) {
      lines.push('\nInternal reference materials:');
      lines.push(this.formatChunksForPrompt(chunks));
    }

    // Output style guidance
    lines.push(
      '\nWhen useful, structure your response with a brief answer, then optional steps or troubleshooting guidance.'
    );

    return lines.join('\n');
  }

  /**
   * Helper: Build user message with text and images
   *
   * Creates message content array with text and vision components
   */
  private buildUserMessage(userPrompt: string, images: string[]): any {
    this.logger.debug(`Building user message with ${images.length} images`);
    const content: Array<any> = [];
    content.push({ type: 'text', text: userPrompt });
    for (const url of images || []) {
      if (typeof url === 'string' && url.trim().length > 0) {
        content.push({ type: 'image_url', image_url: { url } });
      }
    }
    return content;
  }

  /**
   * Helper: Format chunks into readable context
   */
  private formatChunksForPrompt(chunks: KnowledgeChunkData[]): string {
    const MAX_PER_CHUNK_CHARS = 600;
    const parts: string[] = [];
    chunks.forEach((c, idx) => {
      const title = c.heading?.trim() || `Chunk ${idx + 1}`;
      const source = c.sourceId ? ` (source: ${c.sourceId})` : '';
      const text = (c.content || '').replace(/\s+/g, ' ').trim();
      const snippet = text.length > MAX_PER_CHUNK_CHARS ? text.slice(0, MAX_PER_CHUNK_CHARS) + '…' : text;
      parts.push(`[${title}]${source}: ${snippet}`);
    });
    return parts.join('\n');
  }

  /**
   * Helper: Call OpenAI streaming API
   */
  private async *callOpenAIStream(
    systemPrompt: string,
    userMessage: any,
  ): AsyncGenerator<string> {
    const stream = await this.openai.chat.completions.create({
      model: this.MODEL_ID,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userMessage },
      ],
      temperature: this.TEMPERATURE,
      max_tokens: this.MAX_TOKENS,
      stream: true,
    });

    // Iterate over streamed chunks and yield token content
    for await (const part of stream as any) {
      try {
        const delta = part?.choices?.[0]?.delta;
        const token = delta?.content ?? '';
        if (token) {
          yield token;
        }
      } catch (err) {
        // Ignore malformed parts; continue streaming
        this.logger.warn(`Malformed stream part encountered: ${String(err)}`);
      }
    }
  }
}
