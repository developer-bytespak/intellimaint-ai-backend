import { Injectable, Logger } from '@nestjs/common';
import { GoogleGenerativeAI } from '@google/generative-ai';
import { appConfig } from '../../../config/app.config';

interface ChatMessage {
  role: 'user' | 'model';
  parts: Array<{ text: string } | { inlineData: { data: string; mimeType: string } }>;
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
export class GeminiChatService {
  private readonly logger = new Logger(GeminiChatService.name);
  private genAI: GoogleGenerativeAI;
  private model: any;
  private sessionImageCache: Map<string, ImageData[]> = new Map();
  private sessionCachedContent: Map<string, CachedSession> = new Map();
  // Track active streams to allow cancellation
  private activeStreams: Map<string, AbortController> = new Map();

  constructor() {
    const apiKey = appConfig.gemini.apiKey;
    if (!apiKey) {
      throw new Error('GEMINI_API_KEY is not configured');
    }

    this.genAI = new GoogleGenerativeAI(apiKey);
    this.model = this.genAI.getGenerativeModel({
      model: appConfig.gemini.modelName,
    });
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
   * Check if cached content is still valid for this session
   * Note: The current @google/generative-ai SDK (v0.24.1) doesn't expose the cacheContent API yet.
   * This is a placeholder for when the SDK supports it. For now, we track sessions to reuse
   * the same images without re-encoding them, which provides some performance benefit.
   */
  private async getOrCreateCachedContent(
    sessionId: string,
    images: ImageData[],
  ): Promise<string | null> {
    if (images.length === 0) return null;

    try {
      // Check if we have valid cached content
      const cached = this.sessionCachedContent.get(sessionId);
      if (cached && cached.expiresAt > Date.now()) {
        this.logger.debug(`Using existing session cache for ${sessionId}`);
        return cached.cachedContentName;
      }

      // Create a session identifier based on images
      const imageHashes = images.map((img) => this.hashImage(img.data));
      const sessionKey = `session-${sessionId}-${imageHashes.join('-')}`;
      const expiresAt = Date.now() + 3600 * 1000; // 1 hour from now

      this.sessionCachedContent.set(sessionId, {
        cachedContentName: sessionKey,
        expiresAt,
        imageHashes,
      });

      this.logger.debug(
        `Session cache created for ${sessionId}, expires at ${new Date(expiresAt).toISOString()}`,
      );

      // Return null for now since SDK doesn't support cacheContent yet
      // When SDK is updated, this will return the actual cached content name
      return null;
    } catch (error) {
      this.logger.warn('Failed to create session cache:', error.message);
      return null;
    }
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
          role: 'user',
          parts: [{ text: summaryMessage }],
        });
        totalChars += summaryMessage.length;
      }
    }

    for (const msg of recentMessages) {
      const content = msg.content || '';
      if (totalChars + content.length > maxChars) break;

      const role = msg.role === 'user' ? 'user' : 'model';
      history.push({
        role,
        parts: [{ text: content }],
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

      const response = await this.model.generateContent(summaryPrompt);
      const summaryText = response.response?.text() || response.text() || '';

      return summaryText.trim();
    } catch (error) {
      this.logger.error('Error summarizing messages:', error);
      return `Previous conversation with ${messages.length} messages about technical troubleshooting.`;
    }
  }

  /**
   * Convert base64 image to Gemini inline data format
   */
  private imageToInlineData(
    base64: string,
    mimeType: string = 'image/jpeg',
  ): { inlineData: { data: string; mimeType: string } } {
    const cleanBase64 = base64.includes(',') ? base64.split(',')[1] : base64;

    return {
      inlineData: {
        data: cleanBase64,
        mimeType,
      },
    };
  }

  /**
   * Generate chat response with Gemini
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
      const parts: Array<{ text: string } | { inlineData: { data: string; mimeType: string } }> = [];

      for (const img of sessionImages) {
        parts.push(this.imageToInlineData(img.data, img.mimeType));
      }

      parts.push({ text: prompt });

      const startTime = Date.now();

      // Try to use cached content if available
      const cachedContentName = await this.getOrCreateCachedContent(sessionId, sessionImages);

      let response: any;
      try {
        if (history.length > 0) {
          const chat = this.model.startChat({ history });
          if (cachedContentName) {
            response = await chat.sendMessage(parts, {
              cachedContent: cachedContentName,
            });
          } else {
            response = await chat.sendMessage(parts);
          }
        } else {
          if (cachedContentName) {
            response = await this.model.generateContent(
              { contents: [{ role: 'user', parts }] },
              { cachedContent: cachedContentName },
            );
          } else {
            response = await this.model.generateContent(parts);
          }
        }
      } catch (apiError) {
        this.logger.error('Gemini API call failed:', apiError);
        throw apiError;
      }

      let usageMetadata: any = null;
      
      if (response && typeof response === 'object' && response !== null) {
        try {
          if (response.response?.usageMetadata) {
            usageMetadata = response.response.usageMetadata;
          } else if (response.usageMetadata) {
            usageMetadata = response.usageMetadata;
          } else if (response.usage?.metadata) {
            usageMetadata = response.usage.metadata;
          }
        } catch (error) {
          this.logger.warn('Error accessing usage metadata:', error);
        }
      }

      const tokenUsage: TokenUsage = {
        promptTokens: usageMetadata?.promptTokenCount ?? null,
        completionTokens: usageMetadata?.candidatesTokenCount ?? null,
        cachedTokens: usageMetadata?.cachedContentTokenCount ?? null,
        totalTokens: usageMetadata?.totalTokenCount ?? null,
      };

      const endTime = Date.now();
      const responseTime = endTime - startTime;
      const responseTimeInSeconds = (responseTime / 1000).toFixed(2);

      console.log(`[Gemini API] Response Time: ${responseTimeInSeconds}s | Tokens - Prompt: ${tokenUsage.promptTokens ?? 'N/A'}, Completion: ${tokenUsage.completionTokens ?? 'N/A'}, Cached: ${tokenUsage.cachedTokens ?? 'N/A'}, Total: ${tokenUsage.totalTokens ?? 'N/A'}`);

      let responseText = '';
      try {
        if (typeof response === 'string') {
          responseText = response;
        } else if (response && typeof response === 'object' && response !== null) {
          if (response.response) {
            if (typeof response.response.text === 'function') {
              responseText = response.response.text() || '';
            } else if (typeof response.response.text === 'string') {
              responseText = response.response.text;
            } else if (typeof response.response === 'string') {
              responseText = response.response;
            }
          }
          
          if (!responseText && response.text) {
            if (typeof response.text === 'function') {
              responseText = response.text();
            } else if (typeof response.text === 'string') {
              responseText = response.text;
            }
          }
          
          if (!responseText && response.candidates) {
            if (Array.isArray(response.candidates) && response.candidates.length > 0) {
              const candidate = response.candidates[0];
              if (candidate?.content?.parts && Array.isArray(candidate.content.parts)) {
                responseText = candidate.content.parts
                  .map((part: any) => {
                    if (part && typeof part === 'object' && part.text) {
                      return part.text;
                    }
                    return '';
                  })
                  .filter((text: string) => text.length > 0)
                  .join('');
              }
            }
          }
        }
      } catch (error) {
        this.logger.error('Error extracting response text:', error);
        responseText = '';
      }

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

      const parts: Array<{ text: string } | { inlineData: { data: string; mimeType: string } }> = [];

      for (const img of sessionImages) {
        parts.push(this.imageToInlineData(img.data, img.mimeType));
      }

      parts.push({ text: prompt });

      const startTime = Date.now();

      let fullResponseText = '';
      let usageMetadata: any = null;

      // Try to use cached content if available
      const cachedContentName = await this.getOrCreateCachedContent(sessionId, sessionImages);

      let result: any;
      
      if (history.length > 0) {
        const chat = this.model.startChat({ history });
        if (cachedContentName) {
          result = await chat.sendMessageStream(parts, {
            cachedContent: cachedContentName,
          });
        } else {
          result = await chat.sendMessageStream(parts);
        }
      } else {
        if (cachedContentName) {
          result = await this.model.generateContentStream(
            { contents: [{ role: 'user', parts }] },
            { cachedContent: cachedContentName },
          );
        } else {
          result = await this.model.generateContentStream(parts);
        }
      }

      // OPTIMIZED: Send 6-8 character chunks
      // This balances network efficiency with smooth frontend display
      const CHARS_PER_YIELD = 7;
      
      let buffer = '';
      let isAborted = false;

      // Stream chunks from Gemini and break into optimal tokens
      try {
        for await (const chunk of result.stream) {
          // Check if stream was aborted
          if (abortSignal?.aborted) {
            this.logger.debug(`Stream aborted via signal for session ${sessionId}`);
            isAborted = true;
            break;
          }

          const chunkText = chunk.text();
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

      // Get final response for token usage
      const finalResponse = await result.response;
      
      try {
        if (finalResponse?.usageMetadata) {
          usageMetadata = finalResponse.usageMetadata;
        } else if (finalResponse?.response?.usageMetadata) {
          usageMetadata = finalResponse.response.usageMetadata;
        } else if (result?.usageMetadata) {
          usageMetadata = result.usageMetadata;
        }
        
        // Log the actual response structure for debugging
        this.logger.debug('Final response structure:', JSON.stringify({
          hasUsageMetadata: !!finalResponse?.usageMetadata,
          hasResponseUsageMetadata: !!finalResponse?.response?.usageMetadata,
          usageMetadata: usageMetadata,
        }));
      } catch (error) {
        this.logger.warn('Error accessing usage metadata:', error);
      }

      const tokenUsage: TokenUsage = {
        promptTokens: usageMetadata?.promptTokenCount ?? null,
        completionTokens: usageMetadata?.candidatesTokenCount ?? null,
        cachedTokens: usageMetadata?.cachedContentTokenCount ?? null,
        totalTokens: usageMetadata?.totalTokenCount ?? null,
      };

      const endTime = Date.now();
      const responseTime = endTime - startTime;
      const responseTimeInSeconds = (responseTime / 1000).toFixed(2);

      console.log(`[Gemini API Stream] Response Time: ${responseTimeInSeconds}s | Tokens - Prompt: ${tokenUsage.promptTokens ?? 'N/A'}, Completion: ${tokenUsage.completionTokens ?? 'N/A'}, Cached: ${tokenUsage.cachedTokens ?? 'N/A'}, Total: ${tokenUsage.totalTokens ?? 'N/A'}`);

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
      
      this.logger.error('Gemini streaming API call failed:', error);
      throw error;
    }
  }
}