/**
 * Chat Title Generation Service
 *
 * This service handles automatic generation of meaningful chat session titles
 * from the user's first message using LLM.
 *
 * Responsibilities:
 * - Generate concise, descriptive titles from user messages
 * - Use OpenAI to create contextually relevant titles
 * - Fallback to truncated message if LLM fails
 */

import { Injectable, Logger } from '@nestjs/common';
import OpenAI from 'openai';

@Injectable()
export class ChatTitleService {
  private readonly logger = new Logger(ChatTitleService.name);
  private readonly openai: OpenAI;
  private readonly MODEL_ID = 'gpt-4o-mini'; // Use faster model for title generation
  private readonly MAX_TITLE_LENGTH = 60; // Characters

  constructor() {
    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey) {
      throw new Error('OPENAI_API_KEY environment variable not configured');
    }
    this.openai = new OpenAI({ apiKey });
  }

  /**
   * Generate a suitable title for a chat session based on the first user message
   *
   * @param userMessage - The first message from the user
   * @param imageCount - Number of images in the message (optional)
   * @returns A concise, descriptive title (max 60 chars)
   */
  async generateTitle(userMessage: string, imageCount: number = 0): Promise<string> {
    try {
      // Fallback for very short messages or images-only
      if (!userMessage || userMessage.trim().length === 0) {
        return imageCount > 0 ? 'Image Analysis' : 'New Chat';
      }

      const messagePreview = userMessage.substring(0, 500); // Use first 500 chars for context

      const response = await this.openai.chat.completions.create({
        model: this.MODEL_ID,
        messages: [
          {
            role: 'system',
            content: `You are a helpful assistant that creates concise, descriptive titles for chat conversations.
            
Generate a short title (maximum 6 words or ${this.MAX_TITLE_LENGTH} characters) that captures the main topic or question from the user's message.
The title should be:
- Concise and descriptive
- In the same language as the user's message
- Free of punctuation at the end
- Suitable as a chat session title

Respond with ONLY the title, nothing else.`,
          },
          {
            role: 'user',
            content: `Create a title for this message: "${messagePreview}"`,
          },
        ],
        max_tokens: 20, // Very short response
        temperature: 0.5, // Lower temperature for consistency
      });

      const title =
        response.choices[0]?.message?.content?.trim() ||
        'New Chat';

      // Validate and clean the title
      const cleanedTitle = this.validateAndCleanTitle(title);

      this.logger.debug(
        `Generated title from message: "${userMessage.substring(0, 50)}..." -> "${cleanedTitle}"`,
      );

      return cleanedTitle;
    } catch (error: any) {
      this.logger.warn(
        `Failed to generate title using LLM, falling back to message truncation: ${error.message}`,
      );

      // Fallback: truncate original message
      return this.getFallbackTitle(userMessage, imageCount);
    }
  }

  /**
   * Validate and clean the generated title
   *
   * @param title - The title to validate
   * @returns Cleaned title with length constraints
   */
  private validateAndCleanTitle(title: string): string {
    // Remove quotes if present
    let cleaned = title.replace(/^["']|["']$/g, '').trim();

    // Remove trailing punctuation
    cleaned = cleaned.replace(/[.,;:!?]+$/, '');

    // Truncate if too long
    if (cleaned.length > this.MAX_TITLE_LENGTH) {
      cleaned = cleaned.substring(0, this.MAX_TITLE_LENGTH - 3) + '...';
    }

    // Ensure title is not empty
    return cleaned.length > 0 ? cleaned : 'New Chat';
  }

  /**
   * Fallback title generation from truncated message
   *
   * @param message - The user message
   * @param imageCount - Number of images
   * @returns Truncated message as fallback title
   */
  private getFallbackTitle(message: string, imageCount: number): string {
    if (!message || message.trim().length === 0) {
      return imageCount > 0 ? 'Image Analysis' : 'New Chat';
    }

    // Truncate message to reasonable length
    const maxLength = this.MAX_TITLE_LENGTH;
    if (message.length > maxLength) {
      return message.substring(0, maxLength - 3) + '...';
    }

    return message;
  }
}
