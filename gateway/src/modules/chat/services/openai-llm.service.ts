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
   * @returns Async generator yielding response tokens and usage data
   *
   * Steps:
   * 1. Build system prompt with role, context, and knowledge chunks
   * 2. Build user message with prompt text and images
   * 3. Open streaming connection to OpenAI gpt-4o
   * 4. Yield each token as received from API
   * 5. Yield usage data in final chunk
   * 6. Handle errors gracefully
   */
  async *streamCompletion(
    userPrompt: string,
    contextSummary: string,
    chunks: KnowledgeChunkData[],
    images: string[],
    imageSummaries: string[] = [],
    imageSummariesNote?: string,
  ): AsyncGenerator<{ token?: string; usage?: any }> {
    this.logger.debug(
      `Starting LLM stream with ${chunks.length} chunks and ${images.length} images`,
    );

    // Build prompts
    const systemPrompt = this.buildSystemPrompt(contextSummary, chunks, imageSummaries, imageSummariesNote);
    const userMessage = this.buildUserMessage(userPrompt, images);

    // Call OpenAI streaming API and yield tokens
    try {
      for await (const chunk of this.callOpenAIStream(systemPrompt, userMessage)) {
        yield chunk;
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
  private buildSystemPrompt(contextSummary: string, chunks: KnowledgeChunkData[], imageSummaries: string[] = [], imageSummariesNote?: string): string {
    this.logger.debug(`Building system prompt with ${chunks.length} chunks`);
    const lines: string[] = [];

    // Role and interaction policy: user-focused, no backend/source disclosure
    lines.push(
      'You are IntelliMaint, a helpful maintenance assistant. Answer clearly and concisely. '
      + 'Do not mention internal systems, databases, or sources. '
    );

    // Adaptive behavior based on context availability
    if (chunks && chunks.length > 0) {
      lines.push(
        'If provided context includes relevant information, use it to ground your answer. '
        + 'If information is insufficient, respond naturally using your knowledge. '
        + 'Do not invent part numbers/specs unless clearly visible or provided.'
      );
    } else {
      lines.push(
        'No specific reference materials are available for this query. '
        + 'Respond naturally using your general knowledge. '
        + 'For generic greetings or chitchat, keep responses brief and friendly. '
        + 'For technical questions, provide helpful guidance based on common maintenance practices, '
        + 'but acknowledge when specific documentation would be needed for detailed repair steps.'
      );
    }

    // Visual guidance for image-based queries
    lines.push(
      '\nWhen images are provided:'
      + '\n- Analyze visible features (components, connectors, damage, labels)'
      + '\n- Identify device type/category when possible (smartphone, laptop, tablet, appliance, etc.)'
      + '\n- Reference what you observe: "I can see...", "Based on the visible..."'
      + '\n- Provide guidance based on visual cues even if exact model is unknown'
      + '\n- Only request specific model/brand if critical for the repair step and not visually determinable'
    );

    // Include brief conversation summary when available
    if (contextSummary && contextSummary.trim().length > 0) {
      lines.push('\nConversation summary (for context):');
      lines.push(contextSummary.trim());
    }

    // Include prior image summaries (stored vision outputs) if available
    if (imageSummaries && imageSummaries.length > 0) {
      lines.push('\nPrior images (summaries from past uploads):');
      imageSummaries.forEach((desc, idx) => {
        lines.push(`- Image #${idx + 1} (most recent first): ${desc}`);
      });
      if (imageSummariesNote) {
        lines.push(`Note: ${imageSummariesNote}`);
      }
      lines.push(
        'If the user refers to an image, use the closest summary above. '
        + 'If the request needs visual details not present in these summaries (e.g., serial numbers, fine print), ask the user to resend the image.'
      );
    }

    // Knowledge chunks formatted for internal grounding (not shown to user)
    // Only include this section if chunks exist
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
   * Chunks are sorted by sourceId and chunkIndex to maintain document coherence
   * when adjacent chunks are included for context expansion
   * 
   * Note: Chunks can be up to 600 tokens (~2400 chars), so we use a higher limit
   * to ensure important information at the end of chunks isn't truncated.
   */
  private formatChunksForPrompt(chunks: KnowledgeChunkData[]): string {
    // Allow up to 3000 chars per chunk to match chunking config (max 600 tokens ≈ 2400 chars)
    // Adding buffer for safety
    const MAX_PER_CHUNK_CHARS = 3000;
    const parts: string[] = [];
    
    // Group chunks by sourceId for better context presentation
    const chunksBySource = new Map<string, KnowledgeChunkData[]>();
    for (const chunk of chunks) {
      const sourceChunks = chunksBySource.get(chunk.sourceId) || [];
      sourceChunks.push(chunk);
      chunksBySource.set(chunk.sourceId, sourceChunks);
    }
    
    // Sort chunks within each source by chunkIndex for coherent reading order
    for (const [sourceId, sourceChunks] of chunksBySource) {
      sourceChunks.sort((a, b) => (a.chunkIndex ?? 0) - (b.chunkIndex ?? 0));
      
      sourceChunks.forEach((c) => {
        const chunkLabel = c.chunkIndex !== undefined ? `Chunk ${c.chunkIndex}` : '';
        const title = c.heading?.trim() || chunkLabel || 'Content';
        const sourceInfo = ` (source: ${sourceId}${chunkLabel ? `, ${chunkLabel}` : ''})`;
        const text = (c.content || '').replace(/\s+/g, ' ').trim();
        const snippet = text.length > MAX_PER_CHUNK_CHARS ? text.slice(0, MAX_PER_CHUNK_CHARS) + '…' : text;
        parts.push(`[${title}]${sourceInfo}: ${snippet}`);
      });
    }
    
    return parts.join('\n');
  }

  /**
   * Helper: Call OpenAI streaming API
   */
  private async *callOpenAIStream(
    systemPrompt: string,
    userMessage: any,
  ): AsyncGenerator<{ token?: string; usage?: any }> {
    const stream = await this.openai.chat.completions.create({
      model: this.MODEL_ID,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userMessage },
      ],
      temperature: this.TEMPERATURE,
      max_tokens: this.MAX_TOKENS,
      stream: true,
      stream_options: { include_usage: true },
    });

    // Iterate over streamed chunks and yield token content
    for await (const part of stream as any) {
      try {
        const delta = part?.choices?.[0]?.delta;
        const token = delta?.content ?? '';
        const usage = part?.usage;
        
        if (token) {
          yield { token };
        }
        
        // Usage data comes in the final chunk
        if (usage) {
          this.logger.debug(`Token usage: ${JSON.stringify(usage)}`);
          yield { usage };
        }
      } catch (err) {
        // Ignore malformed parts; continue streaming
        this.logger.warn(`Malformed stream part encountered: ${String(err)}`);
      }
    }
  }
}
