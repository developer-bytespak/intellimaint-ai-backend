/**
 * OpenAI Vision Service
 *
 * Handles image analysis using OpenAI's GPT-4o Vision API.
 * Analyzes images for scene descriptions and stores results in database.
 *
 * Responsibilities:
 * - Call GPT-4o Vision API with base64 images
 * - Extract detailed scene descriptions
 * - Store analysis results in ImageAnalysis table
 * - Return structured analysis for pipeline consumption
 *
 * Data Flow:
 * - Input: messageId + Array<{ base64: string, mimeType: string }>
 * - Output: Array<ImageAnalysisResult> with descriptions
 * - Storage: ImageAnalysis table with sceneDescription: { description: "..." }
 *
 * Error Handling:
 * - Skip individual failed images (prevents one bad image from blocking pipeline)
 * - Retry transient failures with exponential backoff
 * - Log warnings but continue processing
 */

import { Injectable, Logger } from '@nestjs/common';
import OpenAI from 'openai';
import { PrismaService } from 'prisma/prisma.service';
import { ImageAnalysisResult } from '../dto/pipeline-message.dto';

// Input can be either a direct URL string or base64 data with MIME type
type ImageInput = string | { base64: string; mimeType: string };

@Injectable()
export class OpenAIVisionService {
  private readonly logger = new Logger(OpenAIVisionService.name);
  private readonly openai: OpenAI;
  private readonly maxRetries = 3;
  private readonly retryBaseDelayMs = 100;

  constructor(
    private readonly prisma: PrismaService,
  ) {
    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey) {
      throw new Error('OPENAI_API_KEY environment variable not configured');
    }
    this.openai = new OpenAI({ apiKey });
  }

  /**
   * Analyze and store images from user message
   *
   * Main entry point for image analysis in pipeline:
   * 1. Convert base64 images to data URLs
   * 2. Call GPT-4o Vision API for each image
   * 3. Store analysis results in ImageAnalysis table
   * 4. Return descriptions for pipeline consumption
   *
   * @param messageId - FK to ChatMessage for linking analysis results
  * @param images - Array of image inputs (URL strings or base64+mimeType)
   * @returns Array of ImageAnalysisResult with descriptions
   */
  async analyzeAndStoreImages(
    messageId: string,
    images: ImageInput[],
  ): Promise<ImageAnalysisResult[]> {
    if (!images || images.length === 0) {
      this.logger.warn('No images provided for analysis');
      return [];
    }

    this.logger.debug(`Analyzing ${images.length} images for message ${messageId}`);

    const results: ImageAnalysisResult[] = [];
    const failedCount = { count: 0 };

    // Process each image sequentially with retry logic
    for (let i = 0; i < images.length; i++) {
      try {
        const result = await this.analyzeImageWithRetry(messageId, images[i], i + 1, images.length);
        if (result) {
          results.push(result);
        }
      } catch (error) {
        failedCount.count++;
        this.logger.error(
          `Image ${i + 1}/${images.length} failed after ${this.maxRetries} retries: ${error.message}`,
        );
        // Continue to next image - non-critical failure
      }
    }

    this.logger.debug(
      `✅ Image analysis complete: ${results.length}/${images.length} successful${failedCount.count > 0 ? `, ${failedCount.count} failed` : ''}`,
    );
    return results;
  }

  /**
   * Analyze single image with retry logic
   *
   * Retries up to maxRetries times with exponential backoff on transient failures.
   * Logs progress and returns null on permanent failures.
   *
   * @param messageId - Message ID for database storage
  * @param image - Either URL string or base64 image with MIME type
   * @param index - Current image index (for logging)
   * @param total - Total images (for logging)
   * @returns ImageAnalysisResult or null on failure
   */
  private async analyzeImageWithRetry(
    messageId: string,
    image: ImageInput,
    index: number,
    total: number,
  ): Promise<ImageAnalysisResult | null> {
    let lastError: Error | null = null;

    for (let attempt = 1; attempt <= this.maxRetries; attempt++) {
      try {
        // Determine image URL: use direct URL if string, else convert base64 to data URL
        const imageUrl = typeof image === 'string'
          ? image
          : `data:${image.mimeType};base64,${image.base64}`;

        this.logger.debug(
          `[${index}/${total}] Calling GPT-4o Vision (attempt ${attempt}/${this.maxRetries})`,
        );

        // Call OpenAI Vision API
        const response = await this.openai.chat.completions.create({
          model: 'gpt-4o',
          messages: [
            {
              role: 'user',
              content: [
                {
                  type: 'text',
                  text: 'Analyze this image in detail. Describe the visible objects, components, context, and any relevant details about what you see.',
                },
                {
                  type: 'image_url',
                  image_url: {
                    url: imageUrl,
                  },
                },
              ],
            },
          ],
          max_tokens: 1024,
        });

        const description =
          response.choices[0]?.message?.content || 'Unable to analyze image';

        // Store in ImageAnalysis table
        // First, get the attachment ID for this message's image
        const attachments = await this.prisma.messageAttachment.findMany({
          where: { messageId },
          orderBy: { createdAt: 'asc' },
        });

        const attachment = attachments[index - 1]; // index is 1-based
        if (!attachment) {
          throw new Error(`No attachment found for image ${index}`);
        }

        const analysis = await this.prisma.imageAnalysis.create({
          data: {
            attachmentId: attachment.id,
            sceneDescription: {
              description,
            },
          },
        });

        this.logger.debug(`✅ [${index}/${total}] Image analyzed and stored: ${analysis.id}`);

        return {
          attachmentId: analysis.id,
          description,
        };
      } catch (error) {
        lastError = error;

        // Check if this is a transient error worth retrying
        const isTransient =
          error?.status === 429 || // Rate limit
          error?.status === 500 || // Server error
          error?.status === 503; // Service unavailable

        if (isTransient && attempt < this.maxRetries) {
          const delayMs = Math.pow(2, attempt - 1) * this.retryBaseDelayMs;
          this.logger.warn(
            `[${index}/${total}] Transient error (attempt ${attempt}/${this.maxRetries}), retrying in ${delayMs}ms: ${error.message}`,
          );
          await new Promise((resolve) => setTimeout(resolve, delayMs));
        } else if (attempt === this.maxRetries) {
          // Final attempt failed
          this.logger.error(
            `[${index}/${total}] Failed after ${this.maxRetries} attempts: ${error.message}`,
          );
        }
      }
    }

    // All retries exhausted
    return null;
  }
}
