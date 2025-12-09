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
}

@Injectable()
export class GeminiChatService {
  private readonly logger = new Logger(GeminiChatService.name);
  private genAI: GoogleGenerativeAI;
  private model: any;
  private sessionImageCache: Map<string, ImageData[]> = new Map();

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
   * Cache an image for a session (e.g., broken washing machine image)
   */
  cacheSessionImage(sessionId: string, base64: string, mimeType: string = 'image/jpeg'): void {
    if (!this.sessionImageCache.has(sessionId)) {
      this.sessionImageCache.set(sessionId, []);
    }

    const images = this.sessionImageCache.get(sessionId)!;
    // Avoid duplicates by checking if image already exists
    const exists = images.some((img) => img.data === base64);
    if (!exists) {
      images.push({ data: base64, mimeType });
    }
  }

  /**
   * Get all cached images for a session
   */
  getSessionImages(sessionId: string): ImageData[] {
    return this.sessionImageCache.get(sessionId) || [];
  }

  /**
   * Clear session image cache
   */
  clearSessionCache(sessionId: string): void {
    this.sessionImageCache.delete(sessionId);
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
    const maxChars = maxTokens * 4; // Rough estimate: 1 token ≈ 4 chars

    // Take most recent messages (up to 10)
    const recentMessages = messages.slice(-10);

    // If there's a context summary and we have more than 10 messages, include it
    if (contextSummary && messages.length > 10) {
      // Add summary as a system-like context message
      const summaryMessage = `[Previous conversation summary: ${contextSummary}]`;
      if (totalChars + summaryMessage.length <= maxChars) {
        history.push({
          role: 'user',
          parts: [{ text: summaryMessage }], // FIXED: parts must be array of objects with 'text' property
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
        parts: [{ text: content }], // FIXED: parts must be array of objects with 'text' property
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

      // Format messages for summarization
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
      // Return a basic summary if summarization fails
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
    // Remove data URL prefix if present
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
   * @param sessionId - Session ID for image caching
   * @param prompt - User's prompt text
   * @param messages - Conversation history
   * @param newImages - Optional new images to include (base64 with mimeType)
   * @param contextSummary - Optional summary of older messages beyond the window
   * @returns Response text and token usage
   */
  async generateChatResponse(
    sessionId: string,
    prompt: string,
    messages: Array<{ role: string; content: string }>,
    newImages?: Array<{ base64: string; mimeType: string }>,
    contextSummary?: string | null,
  ): Promise<{ response: string; tokenUsage: TokenUsage }> {
    try {
      // Validate prompt is not empty
      if (!prompt || prompt.trim().length === 0) {
        throw new Error('Prompt cannot be empty');
      }
      // Get session images (persistent broken machine image)
      let sessionImages = this.getSessionImages(sessionId);

      // Cache new images if provided
      if (newImages && newImages.length > 0) {
        for (const img of newImages) {
          this.cacheSessionImage(sessionId, img.base64, img.mimeType);
        }
        // Get updated session images (now includes newly cached images)
        sessionImages = this.getSessionImages(sessionId);
      }

      // Build conversation history with context summary
      const history = this.buildHistory(messages, contextSummary);

      // Prepare content parts
      // Structure: images first (to maximize implicit caching), then prompt
      // IMPORTANT: parts must be array of objects with 'text' or 'inlineData' property
      const parts: Array<{ text: string } | { inlineData: { data: string; mimeType: string } }> = [];

      // Add all session images (includes persistent images + newly cached images)
      // This ensures the broken machine image persists across all messages
      for (const img of sessionImages) {
        parts.push(this.imageToInlineData(img.data, img.mimeType));
      }

      // Add prompt (text comes after images to maximize implicit caching)
      // FIXED: prompt must be wrapped in object with 'text' property
      parts.push({ text: prompt });

      // Generate response
      let response: any;
      try {
        if (history.length > 0) {
          const chat = this.model.startChat({ history });
          response = await chat.sendMessage(parts);
        } else {
          response = await this.model.generateContent(parts);
        }
      } catch (apiError) {
        this.logger.error('Gemini API call failed:', apiError);
        this.logger.error('API Error details:', {
          message: apiError.message,
          code: apiError.code,
          status: apiError.status,
          response: apiError.response?.data || apiError.response,
        });
        throw apiError;
      }

      // Log response structure for debugging (be careful not to log huge objects)
      try {
        this.logger.debug('Gemini response structure:', {
          hasResponse: !!response,
          responseType: typeof response,
          responseIsNull: response === null,
          responseIsArray: Array.isArray(response),
          responseKeys: response && typeof response === 'object' && !Array.isArray(response) && response !== null 
            ? Object.keys(response).slice(0, 10) 
            : 'not an object',
          responseValuePreview: typeof response === 'string' 
            ? response.substring(0, 100) 
            : (response && typeof response === 'object' ? '[object]' : 'not a string'),
        });
      } catch (logError) {
        this.logger.warn('Could not log response structure:', logError);
      }

      // Extract token usage - handle different response structures
      // Gemini API returns usage metadata in different places depending on response type
      let usageMetadata: any = null;
      
      // Check if response is an object (not a string or primitive)
      if (response && typeof response === 'object' && response !== null) {
        try {
          if (response.response && typeof response.response === 'object' && response.response !== null) {
            if (response.response.usageMetadata) {
              usageMetadata = response.response.usageMetadata;
            }
          }
          
          if (!usageMetadata && response.usageMetadata) {
            usageMetadata = response.usageMetadata;
          }
          
          if (!usageMetadata && response.usage && typeof response.usage === 'object') {
            usageMetadata = response.usage.metadata;
          }
        } catch (error) {
          this.logger.warn('Error accessing usage metadata:', error);
        }
      }

      // Log if we can't find usage metadata (for debugging)
      if (!usageMetadata) {
        this.logger.warn('Token usage metadata not found in Gemini response', {
          responseType: typeof response,
          hasResponse: response && typeof response === 'object' ? !!response.response : false,
        });
      }

      const tokenUsage: TokenUsage = {
        promptTokens: usageMetadata?.promptTokenCount ?? null,
        completionTokens: usageMetadata?.candidatesTokenCount ?? null,
        cachedTokens: usageMetadata?.cachedContentTokenCount ?? null,
        totalTokens: usageMetadata?.totalTokenCount ?? null,
      };

      // Log token usage for monitoring
      this.logger.debug('Token usage extracted', tokenUsage);

      // Extract response text - handle different response structures
      let responseText = '';
      try {
        // Check if response is a string (shouldn't happen, but handle it)
        if (typeof response === 'string') {
          this.logger.warn('Gemini returned string response instead of object');
          responseText = response;
        } else if (response && typeof response === 'object' && response !== null) {
          // Try response.response.text() first (for chat responses)
          // This is the most common structure for @google/generative-ai
          if (response.response) {
            try {
              if (typeof response.response === 'object' && response.response !== null) {
                if (typeof response.response.text === 'function') {
                  responseText = response.response.text() || '';
                } else if (typeof response.response.text === 'string') {
                  responseText = response.response.text;
                }
              } else if (typeof response.response === 'string') {
                // If response.response is a string, use it directly
                responseText = response.response;
              }
            } catch (err) {
              this.logger.warn('Error accessing response.response:', err);
            }
          }
          
          // If still empty, try response.text() directly
          if (!responseText) {
            try {
              if (response.text) {
                if (typeof response.text === 'function') {
                  responseText = response.text();
                } else if (typeof response.text === 'string') {
                  responseText = response.text;
                }
              }
            } catch (err) {
              this.logger.warn('Error accessing response.text:', err);
            }
          }
          
          // If still empty, try candidates structure (for generateContent responses)
          if (!responseText && response.candidates) {
            try {
              if (Array.isArray(response.candidates) && response.candidates.length > 0) {
                const candidate = response.candidates[0];
                if (candidate && typeof candidate === 'object' && candidate !== null) {
                  if (candidate.content && typeof candidate.content === 'object' && candidate.content !== null) {
                    if (candidate.content.parts && Array.isArray(candidate.content.parts)) {
                      responseText = candidate.content.parts
                        .map((part: any) => {
                          // Safely check if part is an object before using 'in' operator
                          if (part && typeof part === 'object' && part !== null && !Array.isArray(part)) {
                            // Use hasOwnProperty or direct property access instead of 'in' operator
                            if (part.text !== undefined && typeof part.text === 'string') {
                              return part.text;
                            }
                          }
                          return '';
                        })
                        .filter((text: string) => text.length > 0)
                        .join('');
                    }
                  }
                }
              }
            } catch (err) {
              this.logger.warn('Error accessing candidates:', err);
            }
          }
        }
        
        // If still empty, log warning with full response structure
        if (!responseText) {
          this.logger.warn('Could not extract response text from Gemini response', {
            responseType: typeof response,
            responseIsNull: response === null,
            responseIsArray: Array.isArray(response),
            responseKeys: response && typeof response === 'object' && !Array.isArray(response) ? Object.keys(response) : 'N/A',
            responsePreview: typeof response === 'string' ? response.substring(0, 100) : JSON.stringify(response).substring(0, 200),
          });
        }
      } catch (error) {
        this.logger.error('Error extracting response text:', error);
        this.logger.error('Error details:', {
          message: error.message,
          stack: error.stack,
          responseType: typeof response,
          responsePreview: typeof response === 'string' ? response.substring(0, 100) : JSON.stringify(response).substring(0, 200),
        });
        responseText = '';
      }

      return {
        response: responseText,
        tokenUsage,
      };
    } catch (error) {
      this.logger.error('Error generating chat response:', error);
      this.logger.error('Error details:', {
        message: error.message,
        stack: error.stack,
        name: error.name,
        response: error.response?.data || error.response,
      });
      throw new Error(`Failed to generate chat response: ${error.message || 'Unknown error'}`);
    }
  }
}

