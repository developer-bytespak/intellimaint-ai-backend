import { Injectable, Logger } from '@nestjs/common';
import OpenAI from 'openai';
import { appConfig } from '../../../config/app.config';

interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string | Array<{ type: string; text?: string; image_url?: { url: string; detail?: string } }>;
}

interface TokenUsage {
  promptTokens?: number | null;
  completionTokens?: number | null;
  cachedTokens?: number | null;
  totalTokens?: number | null;
}

interface ImageData {
  data: string; // base64
  mimeType: string;
  vercelBlobUrl?: string; // Optional: store original Vercel Blob URL
}

interface CachedSession {
  cachedContentName: string;
  expiresAt: number;
  imageHashes: string[]; // Track which images are in this cache
}

@Injectable()
export class OpenAIChatService {
  private readonly logger = new Logger(OpenAIChatService.name);
  private openai: OpenAI;
  private modelName: string;
  private sessionImageCache: Map<string, ImageData[]> = new Map();
  private sessionCachedContent: Map<string, CachedSession> = new Map();
  // Track active streams to allow cancellation
  private activeStreams: Map<string, AbortController> = new Map();

  constructor() {
    const apiKey = appConfig.openai.apiKey;
    if (!apiKey) {
      throw new Error('OPENAI_API_KEY is not configured');
    }

    this.openai = new OpenAI({ apiKey });
    this.modelName = appConfig.openai.modelName;
  }

  /**
   * Register an active stream for a session
   */
  registerStream(sessionId: string, abortController: AbortController): void {
    this.activeStreams.set(sessionId, abortController);
    this.logger.debug(`Stream registered for session ${sessionId}`);
  }

  /**
   * Unregister a stream when it completes
   */
  unregisterStream(sessionId: string): void {
    this.activeStreams.delete(sessionId);
    this.logger.debug(`Stream unregistered for session ${sessionId}`);
  }

  /**
   * Abort an active stream for a session
   */
  abortStream(sessionId: string): boolean {
    const controller = this.activeStreams.get(sessionId);
    if (controller) {
      controller.abort();
      this.logger.log(`Stream aborted for session ${sessionId}`);
      return true;
    }
    this.logger.warn(`No active stream found for session ${sessionId}`);
    return false;
  }

  /**
   * Clear image cache when stopping stream
   */
  clearSessionCache(sessionId: string): void {
    this.sessionImageCache.delete(sessionId);
    this.sessionCachedContent.delete(sessionId);
    this.logger.debug(`Cache cleared for session ${sessionId}`);
  }

  /**
   * Cache an image for a session
   */
  cacheSessionImage(
    sessionId: string,
    base64: string,
    mimeType: string = 'image/jpeg',
    vercelBlobUrl?: string,
  ): void {
    if (!this.sessionImageCache.has(sessionId)) {
      this.sessionImageCache.set(sessionId, []);
    }

    const images = this.sessionImageCache.get(sessionId)!;
    const exists = images.some((img) => img.data === base64);
    if (!exists) {
      images.push({ data: base64, mimeType, vercelBlobUrl });
      // Invalidate cached content when new images are added
      this.sessionCachedContent.delete(sessionId);
    }
  }

  /**
   * Get all cached images for a session
   */
  getSessionImages(sessionId: string): ImageData[] {
    return this.sessionImageCache.get(sessionId) || [];
  }

  /**
   * Simple hash for tracking images
   */
  private hashImage(base64: string): string {
    // Simple hash - take first 20 chars of base64
    return base64.substring(0, 20);
  }

  /**
   * Build conversation history with sliding window and summarization
   */
  private buildHistory(
    messages: Array<{ role: string; content: string }>,
    contextSummary?: string | null,
    maxTokens: number = 10000,
  ): ChatMessage[] {
    const history: ChatMessage[] = [];
    let totalChars = 0;
    const maxChars = maxTokens * 4;

    const recentMessages = messages.slice(-5);

    if (contextSummary && messages.length > 5) {
      const summaryMessage = `[Previous conversation summary: ${contextSummary}]`;
      if (totalChars + summaryMessage.length <= maxChars) {
        history.push({
          role: 'system',
          content: summaryMessage,
        });
        totalChars += summaryMessage.length;
      }
    }

    for (const msg of recentMessages) {
      const content = msg.content || '';
      if (totalChars + content.length > maxChars) break;

      const role = msg.role === 'user' ? 'user' : 'assistant';
      history.push({
        role,
        content,
      });
      totalChars += content.length;
    }

    return history;
  }

  /**
   * Summarize older messages beyond the window
   */
  async summarizeMessages(
    messages: Array<{ role: string; content: string }>,
  ): Promise<string> {
    try {
      if (messages.length === 0) {
        return '';
      }

      const conversationText = messages
        .map((msg) => `${msg.role === 'user' ? 'User' : 'Assistant'}: ${msg.content}`)
        .join('\n\n');

      const summaryPrompt = `Summarize the following conversation, preserving:
1. Key technical details and decisions
2. Important context and background information
3. Problems identified and solutions discussed
4. Any specific instructions or preferences mentioned

Keep the summary concise but comprehensive. Focus on information that would be needed to continue the conversation effectively.

Conversation:
${conversationText}

Summary:`;

      const response = await this.openai.chat.completions.create({
        model: this.modelName,
        messages: [{ role: 'user', content: summaryPrompt }],
        max_tokens: 500,
      });

      const summaryText = response.choices[0]?.message?.content || '';

      return summaryText.trim();
    } catch (error) {
      this.logger.error('Error summarizing messages:', error);
      return `Previous conversation with ${messages.length} messages about technical troubleshooting.`;
    }
  }

  /**
   * Convert base64 image to OpenAI image format
   */
  private imageToOpenAIFormat(
    base64: string,
    mimeType: string = 'image/jpeg',
  ): { type: 'image_url'; image_url: { url: string; detail: string } } {
    const cleanBase64 = base64.includes(',') ? base64.split(',')[1] : base64;

    return {
      type: 'image_url',
      image_url: {
        url: `data:${mimeType};base64,${cleanBase64}`,
        detail: 'auto',
      },
    };
  }

  /**
   * Generate chat response with OpenAI
   */
  async generateChatResponse(
    sessionId: string,
    prompt: string,
    messages: Array<{ role: string; content: string }>,
    newImages?: Array<{ base64: string; mimeType: string }>,
    contextSummary?: string | null,
  ): Promise<{ response: string; tokenUsage: TokenUsage }> {
    try {
      if (!prompt || prompt.trim().length === 0) {
        throw new Error('Prompt cannot be empty');
      }

      let sessionImages = this.getSessionImages(sessionId);

      if (newImages && newImages.length > 0) {
        for (const img of newImages) {
          this.cacheSessionImage(sessionId, img.base64, img.mimeType);
        }
        sessionImages = this.getSessionImages(sessionId);
      }

      const history = this.buildHistory(messages, contextSummary);
      
      // System prompt for technician specialist guidance
      const systemPrompt = {
        role: 'system',
        content: `You are an expert technician specialist assistant for IntelliMaint, providing professional guidance for equipment maintenance, troubleshooting, and repair.

Your responsibilities:
1. **Equipment Identification**: When analyzing images of equipment/machinery:
   - Identify the make, model, and type of equipment if visible
   - If the equipment cannot be clearly identified, politely ask: "To provide the most accurate guidance, could you please share the make and model of this equipment?"
   - Look for visible labels, nameplates, serial numbers, or distinctive features

2. **Professional Guidance**:
   - Provide step-by-step troubleshooting procedures
   - Explain technical concepts clearly for both novice and experienced technicians
   - Include safety warnings when working with electrical, mechanical, or hazardous systems
   - Reference industry standards and best practices

3. **Context-Aware Assistance**:
   - If model information is provided, tailor your advice to that specific equipment
   - Recommend manufacturer-specific procedures when applicable
   - Suggest required tools, parts, or materials for repairs
   - Provide preventive maintenance tips

4. **Communication Style**:
   - Be professional, clear, and concise
   - Use technical terminology appropriately with explanations
   - Ask clarifying questions when needed (model number, symptoms, error codes, etc.)
   - Prioritize safety in all recommendations

5. **When Images Are Provided**:
   - Carefully analyze visible components, damage, or issues
   - Point out specific areas of concern in the image
   - If image quality is poor or angles are unclear, request better photos of specific areas

Remember: Safety first. Always recommend proper lockout/tagout procedures, PPE, and following manufacturer guidelines.`
      };
      
      // Build the user message with images and text
      const userContent: Array<{ type: string; text?: string; image_url?: { url: string; detail: string } }> = [];

      for (const img of sessionImages) {
        userContent.push(this.imageToOpenAIFormat(img.data, img.mimeType));
      }

      userContent.push({ type: 'text', text: prompt });

      const openaiMessages: any[] = [
        systemPrompt,
        ...history,
        { role: 'user', content: userContent },
      ];

      const startTime = Date.now();

      const response = await this.openai.chat.completions.create({
        model: this.modelName,
        messages: openaiMessages,
      });

      const tokenUsage: TokenUsage = {
        promptTokens: response.usage?.prompt_tokens ?? null,
        completionTokens: response.usage?.completion_tokens ?? null,
        cachedTokens: null,
        totalTokens: response.usage?.total_tokens ?? null,
      };

      const endTime = Date.now();
      const responseTime = endTime - startTime;
      const responseTimeInSeconds = (responseTime / 1000).toFixed(2);

      console.log(`[OpenAI API] Response Time: ${responseTimeInSeconds}s | Tokens - Prompt: ${tokenUsage.promptTokens ?? 'N/A'}, Completion: ${tokenUsage.completionTokens ?? 'N/A'}, Total: ${tokenUsage.totalTokens ?? 'N/A'}`);

      const responseText = response.choices[0]?.message?.content || '';

      return {
        response: responseText,
        tokenUsage,
      };
    } catch (error) {
      this.logger.error('Error generating chat response:', error);
      throw new Error(`Failed to generate chat response: ${error.message || 'Unknown error'}`);
    }
  }

  /**
   * Stream chat response with optimized chunking (for true LLM-like experience)
   * Returns an async generator that yields small token chunks for smooth frontend display
   * 
   * OPTIMIZATIONS:
   * - Sends 6-8 character chunks (optimal for network + smooth display)
   * - No artificial delays (frontend handles all pacing)
   * - Efficient buffering to reduce overhead
   * - Frontend's useSmoothStreaming splits into characters for character-by-character display
   */
  async *streamChatResponse(
    sessionId: string,
    prompt: string,
    messages: Array<{ role: string; content: string }>,
    images?: Array<{ base64: string; mimeType: string }>,
    contextSummary?: string | null,
    abortSignal?: AbortSignal,
  ): AsyncGenerator<{ token: string; done: boolean; fullText?: string; tokenUsage?: TokenUsage; aborted?: boolean }> {
    try {
      const history = this.buildHistory(messages, contextSummary);

      let sessionImages = this.getSessionImages(sessionId);

      if (images && images.length > 0) {
        for (const img of images) {
          this.cacheSessionImage(sessionId, img.base64, img.mimeType);
        }
        sessionImages = this.getSessionImages(sessionId);
      }

      // System prompt for technician specialist guidance
      const systemPrompt = {
        role: 'system',
        content: `You are an expert technician specialist assistant for IntelliMaint, providing professional guidance for equipment maintenance, troubleshooting, and repair.

Your responsibilities:
1. **Equipment Identification**: When analyzing images of equipment/machinery:
   - Identify the make, model, and type of equipment if visible
   - If the equipment cannot be clearly identified, politely ask: "To provide the most accurate guidance, could you please share the make and model of this equipment?"
   - Look for visible labels, nameplates, serial numbers, or distinctive features

2. **Professional Guidance**:
   - Provide step-by-step troubleshooting procedures
   - Explain technical concepts clearly for both novice and experienced technicians
   - Include safety warnings when working with electrical, mechanical, or hazardous systems
   - Reference industry standards and best practices

3. **Context-Aware Assistance**:
   - If model information is provided, tailor your advice to that specific equipment
   - Recommend manufacturer-specific procedures when applicable
   - Suggest required tools, parts, or materials for repairs
   - Provide preventive maintenance tips

4. **Communication Style**:
   - Be professional, clear, and concise
   - Use technical terminology appropriately with explanations
   - Ask clarifying questions when needed (model number, symptoms, error codes, etc.)
   - Prioritize safety in all recommendations

5. **When Images Are Provided**:
   - Carefully analyze visible components, damage, or issues
   - Point out specific areas of concern in the image
   - If image quality is poor or angles are unclear, request better photos of specific areas

Remember: Safety first. Always recommend proper lockout/tagout procedures, PPE, and following manufacturer guidelines.`
      };

      // Build the user message with images and text
      const userContent: Array<{ type: string; text?: string; image_url?: { url: string; detail: string } }> = [];

      for (const img of sessionImages) {
        userContent.push(this.imageToOpenAIFormat(img.data, img.mimeType));
      }

      userContent.push({ type: 'text', text: prompt });

      const openaiMessages: any[] = [
        systemPrompt,
        ...history,
        { role: 'user', content: userContent },
      ];

      const startTime = Date.now();

      let fullResponseText = '';
      let promptTokens: number | null = null;
      let completionTokens: number | null = null;
      let totalTokens: number | null = null;

      // OPTIMIZED: Send 6-8 character chunks
      // This balances network efficiency with smooth frontend display
      const CHARS_PER_YIELD = 7;
      
      let buffer = '';
      let isAborted = false;

      // Create stream with OpenAI
      const stream = await this.openai.chat.completions.create({
        model: this.modelName,
        messages: openaiMessages,
        stream: true,
        stream_options: { include_usage: true },
      });

      // Stream chunks from OpenAI and break into optimal tokens
      try {
        for await (const chunk of stream) {
          // Check if stream was aborted
          if (abortSignal?.aborted) {
            this.logger.debug(`Stream aborted via signal for session ${sessionId}`);
            isAborted = true;
            break;
          }

          // Extract usage from the final chunk
          if (chunk.usage) {
            promptTokens = chunk.usage.prompt_tokens ?? null;
            completionTokens = chunk.usage.completion_tokens ?? null;
            totalTokens = chunk.usage.total_tokens ?? null;
          }

          const chunkText = chunk.choices[0]?.delta?.content || '';
          if (chunkText) {
            buffer += chunkText;
            
            // Yield chunks of CHARS_PER_YIELD characters
            while (buffer.length >= CHARS_PER_YIELD) {
              const tokenToYield = buffer.substring(0, CHARS_PER_YIELD);
              buffer = buffer.substring(CHARS_PER_YIELD);
              fullResponseText += tokenToYield;
              
              yield {
                token: tokenToYield,
                done: false,
                fullText: fullResponseText,
              };
            }
          }
        }
      } catch (streamError: any) {
        // If stream was aborted, don't throw - just mark as aborted
        if (abortSignal?.aborted || streamError.name === 'AbortError') {
          this.logger.debug(`Stream aborted for session ${sessionId}`);
          isAborted = true;
        } else {
          throw streamError;
        }
      }
      
      // If stream was aborted, yield abort signal and return
      if (isAborted) {
        yield {
          token: '',
          done: true,
          fullText: fullResponseText,
          aborted: true,
        };
        return;
      }
      
      // Yield any remaining characters in buffer
      if (buffer.length > 0) {
        fullResponseText += buffer;
        yield {
          token: buffer,
          done: false,
          fullText: fullResponseText,
        };
      }

      const tokenUsage: TokenUsage = {
        promptTokens,
        completionTokens,
        cachedTokens: null,
        totalTokens,
      };

      const endTime = Date.now();
      const responseTime = endTime - startTime;
      const responseTimeInSeconds = (responseTime / 1000).toFixed(2);

      console.log(`[OpenAI API Stream] Response Time: ${responseTimeInSeconds}s | Tokens - Prompt: ${tokenUsage.promptTokens ?? 'N/A'}, Completion: ${tokenUsage.completionTokens ?? 'N/A'}, Total: ${tokenUsage.totalTokens ?? 'N/A'}`);

      // Send final message with token usage
      yield {
        token: '',
        done: true,
        fullText: fullResponseText,
        tokenUsage,
      };
    } catch (error) {
      // Check if this is an abort error
      if (error?.name === 'AbortError' || abortSignal?.aborted) {
        this.logger.debug(`Stream aborted via error for session ${sessionId}`);
        yield {
          token: '',
          done: true,
          fullText: '',
          aborted: true,
        };
        return;
      }
      
      this.logger.error('OpenAI streaming API call failed:', error);
      throw error;
    }
  }
}
