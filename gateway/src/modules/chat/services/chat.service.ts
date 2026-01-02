import { Injectable, NotFoundException, ForbiddenException, BadRequestException, Logger } from '@nestjs/common';
import { PrismaService } from 'prisma/prisma.service';
import { UpdateSessionDto } from '../dto/update-session.dto';
import { CreateMessageDto } from '../dto/create-message.dto';
import { ListSessionsQueryDto } from '../dto/list-sessions-query.dto';
import { ChatSessionStatus, MessageRole, AttachmentType, ChatMessage } from '@prisma/client';
import { GeminiChatService } from './gemini-chat.service';
import { ImageUtilService } from './image-util.service';
import { VercelBlobService } from './vercel-blob.service';
import { PipelineMessageDto, PipelineChunk, TokenUsage } from '../dto/pipeline-message.dto';
import { OpenAIVisionService } from './openai-vision.service';
import { OpenAIEmbeddingService } from './openai-embedding.service';
import { RagRetrievalService } from './rag-retrieval.service';
import { ContextManagerService } from './context-manager.service';
import { OpenAILLMService } from './openai-llm.service';

@Injectable()
export class ChatService {
  private readonly logger = new Logger(ChatService.name);
  // Track active SSE requests: requestId -> AbortController
  private activeRequests: Map<string, AbortController> = new Map();

  constructor(
    private prisma: PrismaService,
    private geminiChatService: GeminiChatService,
    private imageUtilService: ImageUtilService,
    private vercelBlobService: VercelBlobService,
    private openaiVisionService: OpenAIVisionService,
    private openaiEmbeddingService: OpenAIEmbeddingService,
    private ragRetrievalService: RagRetrievalService,
    private contextManagerService: ContextManagerService,
    private openaiLLMService: OpenAILLMService,
  ) {}

  /**
   * Retry helper with exponential backoff
   * Retries async function N times before throwing
   * Used for transient database errors
   *
   * @param fn - Async function to retry
   * @param maxRetries - Maximum number of attempts (default: 3)
   * @param delayMs - Initial delay in ms, doubles each attempt (default: 100)
   */
  private async retryAsync<T>(
    fn: () => Promise<T>,
    maxRetries: number = 3,
    delayMs: number = 100,
  ): Promise<T> {
    for (let attempt = 0; attempt < maxRetries; attempt++) {
      try {
        return await fn();
      } catch (error) {
        if (attempt === maxRetries - 1) {
          this.logger.error(
            `❌ Retry failed after ${maxRetries} attempts:`,
            error.message,
          );
          throw error;
        }
        const delay = delayMs * Math.pow(2, attempt);
        this.logger.warn(
          `⚠️ Attempt ${attempt + 1} failed, retrying in ${delay}ms:`,
          error.message,
        );
        await new Promise((resolve) => setTimeout(resolve, delay));
      }
    }
    throw new Error('Retry exhausted');
  }

  /**
   * Register a new SSE request with an abort controller
   * This allows the request to be cancelled if the client disconnects
   */
  registerRequest(requestId: string, abortController: AbortController): void {
    this.activeRequests.set(requestId, abortController);
    this.logger.debug(`Request registered: ${requestId}`);
  }

  /**
   * Check if a request is still active
   */
  isRequestActive(requestId: string): boolean {
    return this.activeRequests.has(requestId);
  }

  /**
   * Unregister a request when it completes or is aborted
   */
  unregisterRequest(requestId: string): void {
    this.activeRequests.delete(requestId);
    this.logger.debug(`Request unregistered: ${requestId}`);
  }

  /**
   * Abort a specific request (called when client disconnects)
   */
  abortRequest(requestId: string): boolean {
    const controller = this.activeRequests.get(requestId);
    if (controller) {
      controller.abort();
      this.logger.log(`Request aborted by client: ${requestId}`);
      return true;
    }
    return false;
  }

  /**
   * Abort all active requests for a session
   */
  abortSessionRequests(sessionId: string): number {
    let abortedCount = 0;
    for (const [requestId, controller] of this.activeRequests.entries()) {
      // Request IDs for existing sessions start with sessionId
      // Request IDs for new sessions start with "new-"
      if (requestId.startsWith(sessionId) || requestId.includes(sessionId)) {
        if (!controller.signal.aborted) {
          controller.abort();
          this.logger.log(`Request aborted for session ${sessionId}: ${requestId}`);
          abortedCount++;
        }
      }
    }
    return abortedCount;
  }

  /**
   * Helper method to verify session exists and ownership
   */
  private async verifySessionAccess(userId: string, sessionId: string) {
    const session = await this.prisma.chatSession.findUnique({
      where: { id: sessionId },
    });

    if (!session) {
      throw new NotFoundException('Chat session not found');
    }

    if (session.userId !== userId) {
      throw new ForbiddenException('You do not have access to this chat session');
    }

    return session;
  }

  async listSessions(userId: string, query: ListSessionsQueryDto) {
    const page = Number(query.page) || 1;
    const limit = Number(query.limit) || 10;
    const skip = (page - 1) * limit;

    const where: any = {
      userId,
    };

    // Only show active and archived sessions (no deleted status since we use hard delete)
    if (query.status) {
      where.status = query.status;
    }

    const [sessions, total] = await Promise.all([
      this.prisma.chatSession.findMany({
        where,
        skip,
        take: limit,
        orderBy: {
          updatedAt: 'desc',
        },
        include: {
          messages: {
            take: 1,
            orderBy: {
              createdAt: 'desc',
            },
            include: {
              attachments: true,
            },
          },
          _count: {
            select: {
              messages: true,
            },
          },
        },
      }),
      this.prisma.chatSession.count({ where }),
    ]);

    return {
      sessions,
      pagination: {
        page,
        limit,
        total,
        totalPages: Math.ceil(total / limit),
      },
    };
  }

  async getSession(userId: string, sessionId: string) {
    // Verify access (will throw if not found or wrong owner)
    await this.verifySessionAccess(userId, sessionId);

    const session = await this.prisma.chatSession.findUnique({
      where: { id: sessionId },
      include: {
        messages: {
          orderBy: {
            createdAt: 'asc',
          },
          include: {
            attachments: true,
          },
        },
      },
    });

    return session;
  }

  async updateSession(userId: string, sessionId: string, dto: UpdateSessionDto) {
    // Verify access (will throw if not found or wrong owner)
    await this.verifySessionAccess(userId, sessionId);

    const updateData: any = {};
    if (dto.title !== undefined) {
      updateData.title = dto.title;
    }
    if (dto.status !== undefined) {
      updateData.status = dto.status;
    }
    if (dto.equipmentContext !== undefined) {
      updateData.equipmentContext = dto.equipmentContext;
    }

    const updatedSession = await this.prisma.chatSession.update({
      where: { id: sessionId },
      data: updateData,
      include: {
        messages: {
          orderBy: {
            createdAt: 'asc',
          },
          include: {
            attachments: true,
          },
        },
      },
    });

    return updatedSession;
  }

  async deleteSession(userId: string, sessionId: string) {
    // Verify ownership
    await this.verifySessionAccess(userId, sessionId);

    // Hard delete: Permanently remove from database
    // This will cascade delete all messages and attachments due to onDelete: Cascade
    await this.prisma.chatSession.delete({
      where: { id: sessionId },
    });

    return { message: 'Chat session deleted successfully' };
  }

  async createMessage(userId: string, sessionId: string, dto: CreateMessageDto) {
    // Validate that we have either content or images
    if ((!dto.content || dto.content.trim().length === 0) && (!dto.images || dto.images.length === 0)) {
      throw new BadRequestException('Message must have either content or images');
    }

    // Verify access (will throw if not found or wrong owner)
    const session = await this.verifySessionAccess(userId, sessionId);

    // Upload images to Vercel Blob if they're not already URLs
    const uploadedImageUrls: string[] = [];
    if (dto.images && dto.images.length > 0) {
      for (const imageUrl of dto.images) {
        try {
          // If it's already a permanent URL (http/https), use it directly
          if (imageUrl.startsWith('http://') || imageUrl.startsWith('https://')) {
            uploadedImageUrls.push(imageUrl);
          } else if (imageUrl.startsWith('data:')) {
            // If it's a data URL, try to upload to Vercel Blob
            try {
              const [header, base64] = imageUrl.split(',');
              const mimeMatch = header.match(/data:([^;]+)/);
              const mimeType = mimeMatch ? mimeMatch[1] : 'image/jpeg';
              const blobUrl = await this.vercelBlobService.uploadBase64Image(base64, mimeType);
              uploadedImageUrls.push(blobUrl);
            } catch (blobError) {
              this.logger.warn(`Failed to upload image to Vercel Blob, using data URL directly:`, blobError.message);
              // If Blob upload fails, use the data URL directly (Gemini can handle it)
              uploadedImageUrls.push(imageUrl);
            }
          } else {
            // For blob URLs or other formats, use as-is
            uploadedImageUrls.push(imageUrl);
          }
        } catch (error) {
          this.logger.error(`Failed to process image:`, error);
          // Fallback to original URL if processing fails
          uploadedImageUrls.push(imageUrl);
        }
      }
    }

    // Create the user message with uploaded image URLs
    const userMessage = await this.prisma.chatMessage.create({
      data: {
        sessionId,
        role: MessageRole.user,
        content: dto.content || '', // Allow empty content if images are present
        attachments: {
          create: [
            // Create image attachments with Vercel Blob URLs
            ...(uploadedImageUrls.map((imageUrl) => ({
              attachmentType: AttachmentType.image,
              fileUrl: imageUrl,
            })) || []),
          ],
        },
      },
      include: {
        attachments: true,
      },
    });

    // Get full session with all messages for context
    const fullSession = await this.prisma.chatSession.findUnique({
      where: { id: sessionId },
      include: {
        messages: {
          orderBy: { createdAt: 'asc' },
          include: { attachments: true },
        },
      },
    });

    // Convert messages to format for Gemini
    const messages = fullSession.messages.map((msg) => ({
      role: msg.role === MessageRole.user ? 'user' : 'model',
      content: msg.content,
    }));

    // Check if we need to summarize older messages
    // Window size is 5 (keep last 5 messages in full context)
    const WINDOW_SIZE = 5;
    const needsSummarization = messages.length > WINDOW_SIZE;
    let contextSummary = session.contextSummary;

    // If we have more than WINDOW_SIZE messages, summarize older ones
    // Regenerate summary every 5 messages (when message count exceeds multiples of 5)
    if (needsSummarization) {
      const olderMessages = messages.slice(0, -WINDOW_SIZE);
      
      // Regenerate summary:
      // 1. If no summary exists, OR
      // 2. If we've added enough messages that we need to update the summary
      // Since window is 5, regenerate every time we exceed 5 messages
      // This ensures summary is always up-to-date with all messages except the last 5
      if (olderMessages.length > 0) {
        try {
          contextSummary = await this.geminiChatService.summarizeMessages(olderMessages);
          // Update session with summary
          await this.prisma.chatSession.update({
            where: { id: sessionId },
            data: { contextSummary },
          });
          this.logger.debug(`Updated context summary for session ${sessionId} (${olderMessages.length} messages summarized, ${WINDOW_SIZE} in window)`);
        } catch (error) {
          this.logger.error('Error generating context summary:', error);
          // Continue without summary if it fails
        }
      }
    }

    // Download and process images from Vercel Blob URLs for Gemini
    const imageDataList: Array<{ base64: string; mimeType: string }> = [];
    if (uploadedImageUrls.length > 0) {
      for (const imageUrl of uploadedImageUrls) {
        const imageData = await this.imageUtilService.downloadImageAsBase64(imageUrl);
        if (imageData) {
          imageDataList.push({
            base64: imageData.base64,
            mimeType: imageData.mimeType,
          });
        }
      }
    }

    // Generate AI response using Gemini with context summary
    let assistantMessage;
    try {
      // Use content or default prompt for images
      const prompt = dto.content?.trim() || (imageDataList.length > 0 ? 'Analyze the provided images and provide insights.' : 'Continue the conversation.');
      
      const { response: responseText, tokenUsage } =
        await this.geminiChatService.generateChatResponse(
          sessionId,
          prompt,
          messages,
          imageDataList.length > 0 ? imageDataList : undefined,
          contextSummary,
        );

      // Create assistant message with token counts
      assistantMessage = await this.prisma.chatMessage.create({
        data: {
          sessionId,
          role: MessageRole.assistant,
          content: responseText,
          model: 'gemini-2.5-flash',
          promptTokens: tokenUsage.promptTokens,
          completionTokens: tokenUsage.completionTokens,
          cachedTokens: tokenUsage.cachedTokens,
          totalTokens: tokenUsage.totalTokens,
        },
      });
    } catch (error) {
      this.logger.error('Error generating AI response:', error);
      this.logger.error('Error details:', {
        message: error.message,
        stack: error.stack,
        name: error.name,
      });
      // Still return user message even if AI response fails
      throw new BadRequestException(
        `Failed to generate AI response: ${error.message || 'Unknown error'}`,
      );
    }

    // Update session's updatedAt timestamp
    await this.prisma.chatSession.update({
      where: { id: sessionId },
      data: {
        updatedAt: new Date(),
        // Auto-generate title from first message if title is null
        ...(session.title === null && {
          title: dto.content && dto.content.length > 50 
            ? dto.content.substring(0, 50) + '...' 
            : (dto.content || 'New chat'),
        }),
      },
    });

    // Return both messages
    return {
      userMessage,
      assistantMessage,
    };
  }

  async createMessageWithSession(userId: string, dto: CreateMessageDto) {
    // Validation is done in controller, but double-check here
    const hasContent = dto.content && dto.content.trim().length > 0;
    const hasImages = dto.images && dto.images.length > 0;
    
    if (!hasContent && !hasImages) {
      this.logger.error('Invalid message: No content or images', { dto });
      throw new BadRequestException('Message must have either content or images');
    }

    // Create session first if it doesn't exist
    const session = await this.prisma.chatSession.create({
      data: {
        userId,
        title: null, // Will be set from first message
        equipmentContext: [],
        status: ChatSessionStatus.active,
      },
    });

    // Upload images to Vercel Blob if they're not already URLs
    const uploadedImageUrls: string[] = [];
    if (dto.images && dto.images.length > 0) {
      for (const imageUrl of dto.images) {
        try {
          // If it's already a permanent URL (http/https), use it directly
          if (imageUrl.startsWith('http://') || imageUrl.startsWith('https://')) {
            uploadedImageUrls.push(imageUrl);
          } else if (imageUrl.startsWith('data:')) {
            // If it's a data URL, upload to Vercel Blob
            const [header, base64] = imageUrl.split(',');
            const mimeMatch = header.match(/data:([^;]+)/);
            const mimeType = mimeMatch ? mimeMatch[1] : 'image/jpeg';
            const blobUrl = await this.vercelBlobService.uploadBase64Image(base64, mimeType);
            uploadedImageUrls.push(blobUrl);
          } else {
            // For blob URLs or other formats, use as-is
            uploadedImageUrls.push(imageUrl);
          }
        } catch (error) {
          this.logger.error(`Failed to upload image to Vercel Blob:`, error);
          // Fallback to original URL if upload fails
          uploadedImageUrls.push(imageUrl);
        }
      }
    }

    // Create the user message with uploaded image URLs
    const userMessage = await this.prisma.chatMessage.create({
      data: {
        sessionId: session.id,
        role: MessageRole.user,
        content: dto.content || '', // Allow empty content if images are present
        attachments: {
          create: [
            // Create image attachments with Vercel Blob URLs
            ...(uploadedImageUrls.map((imageUrl) => ({
              attachmentType: AttachmentType.image,
              fileUrl: imageUrl,
            })) || []),
          ],
        },
      },
      include: {
        attachments: true,
      },
    });

    // Convert messages to format for Gemini (only the user message for new session)
    const messages = [
      {
        role: 'user' as const,
        content: dto.content || 'Analyze the provided images.', // Default prompt if no content
      },
    ];

    // Download and process images from Vercel Blob URLs for Gemini
    const imageDataList: Array<{ base64: string; mimeType: string }> = [];
    if (uploadedImageUrls.length > 0) {
      for (const imageUrl of uploadedImageUrls) {
        const imageData = await this.imageUtilService.downloadImageAsBase64(imageUrl);
        if (imageData) {
          imageDataList.push({
            base64: imageData.base64,
            mimeType: imageData.mimeType,
          });
        }
      }
    }

    // Generate AI response using Gemini (no context summary for new session)
    let assistantMessage;
    try {
      // Use content or default prompt for images
      const prompt = dto.content?.trim() || (imageDataList.length > 0 ? 'Analyze the provided images and provide insights.' : 'Hello');
      
      const { response: responseText, tokenUsage } =
        await this.geminiChatService.generateChatResponse(
          session.id,
          prompt,
          messages,
          imageDataList.length > 0 ? imageDataList : undefined,
          null, // No context summary for new session
        );

      // Create assistant message with token counts
      assistantMessage = await this.prisma.chatMessage.create({
        data: {
          sessionId: session.id,
          role: MessageRole.assistant,
          content: responseText,
          model: 'gemini-2.5-flash',
          promptTokens: tokenUsage.promptTokens,
          completionTokens: tokenUsage.completionTokens,
          cachedTokens: tokenUsage.cachedTokens,
          totalTokens: tokenUsage.totalTokens,
        },
      });
    } catch (error) {
      this.logger.error('Error generating AI response:', error);
      this.logger.error('Error details:', {
        message: error.message,
        stack: error.stack,
        name: error.name,
      });
      // Still return user message even if AI response fails
      throw new BadRequestException(
        `Failed to generate AI response: ${error.message || 'Unknown error'}`,
      );
    }

      // Update session's updatedAt timestamp and set title from first message
      const titleText = dto.content?.trim() || (uploadedImageUrls.length > 0 ? 'Image analysis' : 'New chat');
      const updatedSession = await this.prisma.chatSession.update({
        where: { id: session.id },
        data: {
          updatedAt: new Date(),
          title: titleText.length > 50 ? titleText.substring(0, 50) + '...' : titleText,
        },
      include: {
        messages: {
          orderBy: {
            createdAt: 'asc',
          },
          include: {
            attachments: true,
          },
        },
      },
    });

    return {
      session: updatedSession,
      message: userMessage,
      assistantMessage,
    };
  }

  /**
   * Stream message creation with real-time token streaming
   * Returns an async generator that yields tokens as they arrive
   * Implements proper SSE behavior with abort handling
   */
  async *streamMessage(
    userId: string,
    sessionId: string,
    dto: CreateMessageDto,
    requestId: string,
  ): AsyncGenerator<{ token: string; done?: boolean; fullText?: string; messageId?: string; tokenUsage?: any; aborted?: boolean }> {
    // Validate that we have either content or images
    if ((!dto.content || dto.content.trim().length === 0) && (!dto.images || dto.images.length === 0)) {
      throw new BadRequestException('Message must have either content or images');
    }

    // Verify access
    const session = await this.verifySessionAccess(userId, sessionId);

    // Upload images to Vercel Blob if needed
    const uploadedImageUrls: string[] = [];
    if (dto.images && dto.images.length > 0) {
      for (const imageUrl of dto.images) {
        try {
          if (imageUrl.startsWith('http://') || imageUrl.startsWith('https://')) {
            uploadedImageUrls.push(imageUrl);
          } else if (imageUrl.startsWith('data:')) {
            try {
              const [header, base64] = imageUrl.split(',');
              const mimeMatch = header.match(/data:([^;]+)/);
              const mimeType = mimeMatch ? mimeMatch[1] : 'image/jpeg';
              const blobUrl = await this.vercelBlobService.uploadBase64Image(base64, mimeType);
              uploadedImageUrls.push(blobUrl);
            } catch (blobError) {
              this.logger.warn(`Failed to upload image to Vercel Blob:`, blobError.message);
              uploadedImageUrls.push(imageUrl);
            }
          } else {
            uploadedImageUrls.push(imageUrl);
          }
        } catch (error) {
          this.logger.error(`Failed to process image:`, error);
          uploadedImageUrls.push(imageUrl);
        }
      }
    }

    // Create the user message
    const userMessage = await this.prisma.chatMessage.create({
      data: {
        sessionId,
        role: MessageRole.user,
        content: dto.content || '',
        attachments: {
          create: uploadedImageUrls.map((imageUrl) => ({
            attachmentType: AttachmentType.image,
            fileUrl: imageUrl,
          })),
        },
      },
      include: {
        attachments: true,
      },
    });

    // Get full session with all messages for context
    const fullSession = await this.prisma.chatSession.findUnique({
      where: { id: sessionId },
      include: {
        messages: {
          orderBy: { createdAt: 'asc' },
          include: { attachments: true },
        },
      },
    });

    // Convert messages to format for Gemini
    const messages = fullSession.messages.map((msg) => ({
      role: msg.role === MessageRole.user ? 'user' : 'model',
      content: msg.content,
    }));

    // Check if we need to summarize older messages
    const WINDOW_SIZE = 5;
    const needsSummarization = messages.length > WINDOW_SIZE;
    let contextSummary = session.contextSummary;

    if (needsSummarization) {
      const olderMessages = messages.slice(0, -WINDOW_SIZE);
      if (olderMessages.length > 0) {
        try {
          contextSummary = await this.geminiChatService.summarizeMessages(olderMessages);
          await this.prisma.chatSession.update({
            where: { id: sessionId },
            data: { contextSummary },
          });
        } catch (error) {
          this.logger.error('Error generating context summary:', error);
        }
      }
    }

    // Download and process images for Gemini
    const imageDataList: Array<{ base64: string; mimeType: string }> = [];
    if (uploadedImageUrls.length > 0) {
      for (const imageUrl of uploadedImageUrls) {
        const imageData = await this.imageUtilService.downloadImageAsBase64(imageUrl);
        if (imageData) {
          imageDataList.push({
            base64: imageData.base64,
            mimeType: imageData.mimeType,
          });
        }
      }
    }

    // Stream AI response using Gemini
    const prompt = dto.content?.trim() || (imageDataList.length > 0 ? 'Analyze the provided images and provide insights.' : 'Continue the conversation.');
    
    let assistantMessageId: string | undefined;
    let finalFullText = '';
    let finalTokenUsage: any = null;
    let isAborted = false;
    
    // Create AbortController for this stream and register BEFORE starting
    const streamAbortController = new AbortController();
    this.geminiChatService.registerStream(sessionId, streamAbortController);

    try {
      // Check if request was already aborted before starting stream
      if (!this.isRequestActive(requestId)) {
        this.logger.log(`Request ${requestId} already aborted before stream start`);
        isAborted = true;
        yield {
          token: '',
          done: false,
          aborted: true,
        };
        return;
      }

      // Stream tokens from Gemini with abort signal
      for await (const chunk of this.geminiChatService.streamChatResponse(
        sessionId,
        prompt,
        messages,
        imageDataList.length > 0 ? imageDataList : undefined,
        contextSummary,
        streamAbortController.signal,
      )) {
        // ⭐ CRITICAL: Check abort status at START of every iteration
        if (!this.isRequestActive(requestId) || streamAbortController.signal.aborted) {
          this.logger.log(`Request ${requestId} aborted during streaming`);
          streamAbortController.abort();
          isAborted = true;
          yield {
            token: '',
            done: false,
            aborted: true,
          };
          return;
        }

        if (chunk.aborted) {
          // Stream was aborted - don't save
          this.logger.log(`Stream aborted for session ${sessionId}`);
          isAborted = true;
          yield {
            token: '',
            done: false,
            aborted: true,
          };
          return;
        }

        if (chunk.done) {
          // Final check before saving
          if (!this.isRequestActive(requestId) || streamAbortController.signal.aborted) {
            this.logger.log(`Request ${requestId} aborted before final save`);
            isAborted = true;
            yield {
              token: '',
              done: false,
              aborted: true,
            };
            return;
          }

          // Only save final message if request was NOT aborted
          if (!isAborted) {
            finalFullText = chunk.fullText || '';
            finalTokenUsage = chunk.tokenUsage;
            
            assistantMessageId = (await this.prisma.chatMessage.create({
              data: {
                sessionId,
                role: MessageRole.assistant,
                content: finalFullText,
                model: 'gemini-2.5-flash',
                promptTokens: finalTokenUsage?.promptTokens,
                completionTokens: finalTokenUsage?.completionTokens,
                totalTokens: finalTokenUsage?.totalTokens,
              },
            })).id;

            // Update session updatedAt
            await this.prisma.chatSession.update({
              where: { id: sessionId },
              data: { updatedAt: new Date() },
            });

            // Yield final chunk
            yield {
              token: '',
              done: true,
              fullText: finalFullText,
              messageId: assistantMessageId,
              tokenUsage: finalTokenUsage,
            };
          } else {
            // Request was aborted - don't send done event
            this.logger.log(`Aborted generation will not be stored for session ${sessionId}`);
            yield {
              token: '',
              done: false,
              aborted: true,
            };
          }
        } else {
          // Yield token chunk
          yield {
            token: chunk.token,
            done: false,
            fullText: chunk.fullText,
          };
        }
      }
    } catch (error) {
      // Check if this was an abort error
      if (error?.name === 'AbortError' || streamAbortController.signal.aborted) {
        this.logger.log(`Stream aborted for session ${sessionId}`);
        isAborted = true;
        yield {
          token: '',
          done: false,
          aborted: true,
        };
        return;
      }
      this.logger.error('Error streaming message:', error);
      throw error;
    } finally {
      // Clean up: unregister stream and clear cache
      this.geminiChatService.unregisterStream(sessionId);
      
      // If stream was aborted and a message was created, delete it
      if (isAborted && assistantMessageId) {
        try {
          await this.prisma.chatMessage.delete({
            where: { id: assistantMessageId },
          });
          this.logger.log(`Deleted aborted assistant message ${assistantMessageId} from session ${sessionId}`);
        } catch (deleteError) {
          this.logger.warn(`Failed to delete aborted message ${assistantMessageId}:`, deleteError);
        }
      }
    }
  }

  /**
   * Stream message creation with new session (for first message)
   */
  async *streamMessageWithSession(
    userId: string,
    dto: CreateMessageDto,
    requestId: string,
  ): AsyncGenerator<{ token: string; done: boolean; fullText?: string; sessionId?: string; messageId?: string; tokenUsage?: any; aborted?: boolean }> {
    // Validate
    if ((!dto.content || dto.content.trim().length === 0) && (!dto.images || dto.images.length === 0)) {
      throw new BadRequestException('Message must have either content or images');
    }

    // Upload images
    const uploadedImageUrls: string[] = [];
    if (dto.images && dto.images.length > 0) {
      for (const imageUrl of dto.images) {
        try {
          if (imageUrl.startsWith('http://') || imageUrl.startsWith('https://')) {
            uploadedImageUrls.push(imageUrl);
          } else if (imageUrl.startsWith('data:')) {
            try {
              const [header, base64] = imageUrl.split(',');
              const mimeMatch = header.match(/data:([^;]+)/);
              const mimeType = mimeMatch ? mimeMatch[1] : 'image/jpeg';
              const blobUrl = await this.vercelBlobService.uploadBase64Image(base64, mimeType);
              uploadedImageUrls.push(blobUrl);
            } catch (blobError) {
              uploadedImageUrls.push(imageUrl);
            }
          } else {
            uploadedImageUrls.push(imageUrl);
          }
        } catch (error) {
          uploadedImageUrls.push(imageUrl);
        }
      }
    }

    // Create new session
    const session = await this.prisma.chatSession.create({
      data: {
        userId,
        status: ChatSessionStatus.active,
        title: dto.content?.substring(0, 100) || 'New Chat',
      },
    });

    // Create user message
    const userMessage = await this.prisma.chatMessage.create({
      data: {
        sessionId: session.id,
        role: MessageRole.user,
        content: dto.content || '',
        attachments: {
          create: uploadedImageUrls.map((imageUrl) => ({
            attachmentType: AttachmentType.image,
            fileUrl: imageUrl,
          })),
        },
      },
    });

    // Process images for Gemini
    const imageDataList: Array<{ base64: string; mimeType: string }> = [];
    if (uploadedImageUrls.length > 0) {
      for (const imageUrl of uploadedImageUrls) {
        const imageData = await this.imageUtilService.downloadImageAsBase64(imageUrl);
        if (imageData) {
          imageDataList.push({
            base64: imageData.base64,
            mimeType: imageData.mimeType,
          });
        }
      }
    }

    // Stream AI response
    const prompt = dto.content?.trim() || (imageDataList.length > 0 ? 'Analyze the provided images and provide insights.' : 'Continue the conversation.');
    
    let assistantMessageId: string | undefined;
    let finalFullText = '';
    let finalTokenUsage: any = null;
    let isAborted = false;
    
    // Create AbortController for this stream and register BEFORE starting
    const streamAbortController = new AbortController();
    this.geminiChatService.registerStream(session.id, streamAbortController);

    try {
      // Check if request was already aborted before starting stream
      if (!this.isRequestActive(requestId)) {
        this.logger.log(`Request ${requestId} already aborted before stream start`);
        isAborted = true;
        yield {
          token: '',
          done: false,
          aborted: true,
        };
        return;
      }

      for await (const chunk of this.geminiChatService.streamChatResponse(
        session.id,
        prompt,
        [],
        imageDataList.length > 0 ? imageDataList : undefined,
        null,
        streamAbortController.signal,
      )) {
        // Check abort status at START of every iteration
        if (!this.isRequestActive(requestId) || streamAbortController.signal.aborted) {
          this.logger.log(`Request ${requestId} aborted during streaming for new session`);
          streamAbortController.abort();
          isAborted = true;
          yield {
            token: '',
            done: false,
            aborted: true,
          };
          return;
        }

        if (chunk.aborted) {
          // Stream was aborted - don't save
          this.logger.log(`Stream aborted for new session ${session.id}`);
          isAborted = true;
          yield {
            token: '',
            done: false,
            aborted: true,
          };
          return;
        }

        if (chunk.done) {
          // Final check before saving
          if (!this.isRequestActive(requestId) || streamAbortController.signal.aborted) {
            this.logger.log(`Request ${requestId} aborted before final save for new session`);
            isAborted = true;
            yield {
              token: '',
              done: false,
              aborted: true,
            };
            return;
          }

          finalFullText = chunk.fullText || '';
          finalTokenUsage = chunk.tokenUsage;
          
          // Only create message if NOT aborted
          if (!isAborted) {
            assistantMessageId = (await this.prisma.chatMessage.create({
              data: {
                sessionId: session.id,
                role: MessageRole.assistant,
                content: finalFullText,
                model: 'gemini-2.5-flash',
                promptTokens: finalTokenUsage?.promptTokens,
                completionTokens: finalTokenUsage?.completionTokens,
                totalTokens: finalTokenUsage?.totalTokens,
              },
            })).id;

            await this.prisma.chatSession.update({
              where: { id: session.id },
              data: { updatedAt: new Date() },
            });

            yield {
              token: '',
              done: true,
              fullText: finalFullText,
              sessionId: session.id,
              messageId: assistantMessageId,
              tokenUsage: finalTokenUsage,
            };
          } else {
            // Request was aborted - don't send done event
            this.logger.log(`Aborted generation will not be stored for new session ${session.id}`);
            yield {
              token: '',
              done: false,
              aborted: true,
            };
          }
        } else {
          yield {
            token: chunk.token,
            done: false,
            fullText: chunk.fullText,
            sessionId: session.id,
          };
        }
      }
    } catch (error) {
      // Check if this was an abort error
      if (error?.name === 'AbortError' || streamAbortController.signal.aborted) {
        this.logger.log(`Stream aborted for new session ${session.id}`);
        isAborted = true;
        yield {
          token: '',
          done: false,
          aborted: true,
        };
        return;
      }
      this.logger.error('Error streaming message with session:', error);
      throw error;
    } finally {
      // Clean up: unregister stream
      this.geminiChatService.unregisterStream(session.id);
      
      // If stream was aborted and a message was created, delete it
      if (isAborted && assistantMessageId) {
        try {
          await this.prisma.chatMessage.delete({
            where: { id: assistantMessageId },
          });
          this.logger.log(`Deleted aborted assistant message ${assistantMessageId} from new session ${session.id}`);
        } catch (deleteError) {
          this.logger.warn(`Failed to delete aborted message ${assistantMessageId}:`, deleteError);
        }
      }
    }
  }

  /**
   * Delete incomplete assistant messages (those with empty or no content)
   * Called when a stream is stopped to clean up partial responses
   */
  /**
   * Stop an active stream for a session
   * This aborts the stream immediately without throwing if no stream is active
   */
  async stopStream(userId: string, sessionId: string) {
    try {
      // Verify session belongs to user
      await this.verifySessionAccess(userId, sessionId);
      
      // Abort the Gemini stream FIRST (most important for stopping token usage)
      const geminiAborted = this.geminiChatService.abortStream(sessionId);
      
      // Then abort any active requests for this session (request-based tracking)
      const requestsAborted = this.abortSessionRequests(sessionId);
      
      const wasStreaming = requestsAborted > 0 || geminiAborted;
      
      // Clean up any recent assistant messages that might be from aborted streams
      // Only delete messages from the last 60 seconds to avoid deleting legitimate messages
      if (wasStreaming) {
        try {
          const recentMessages = await this.prisma.chatMessage.findMany({
            where: {
              sessionId,
              role: MessageRole.assistant,
              createdAt: {
                gte: new Date(Date.now() - 60000), // Last 60 seconds
              },
            },
            orderBy: {
              createdAt: 'desc',
            },
            take: 1,
          });

          if (recentMessages.length > 0) {
            await this.prisma.chatMessage.delete({
              where: { id: recentMessages[0].id },
            });
            this.logger.log(
              `Deleted orphaned message ${recentMessages[0].id} from stopped stream in session ${sessionId}`,
            );
          }
        } catch (cleanupError) {
          this.logger.warn(
            `Failed to clean up orphaned messages for session ${sessionId}:`,
            cleanupError,
          );
        }
      }
      
      this.logger.log(`Stop stream called for session ${sessionId}, requests aborted: ${requestsAborted}, gemini aborted: ${geminiAborted}`);
      
      return {
        requestsAborted,
        geminiAborted,
        message: wasStreaming ? 'Stream aborted' : 'No active stream',
      };
    } catch (error) {
      this.logger.error(`Error stopping stream for session ${sessionId}:`, error);
      throw error;
    }
  }

  async deleteIncompleteMessages(userId: string, sessionId: string) {
    try {
      // Verify session belongs to user
      const session = await this.verifySessionAccess(userId, sessionId);
      
      // First, abort any active stream for this session
      const wasStreaming = this.geminiChatService.abortStream(sessionId);
      if (wasStreaming) {
        // Wait a bit for the stream to fully abort
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      
      this.logger.debug(`Cleaning up incomplete messages for session ${sessionId}`);
      
      // Find and delete assistant messages with empty or null content
      const deletedMessages = await this.prisma.chatMessage.deleteMany({
        where: {
          sessionId,
          role: MessageRole.assistant,
          OR: [
            { content: '' },
            { content: null },
          ],
        },
      });
      
      this.logger.log(`Deleted ${deletedMessages.count} incomplete messages for session ${sessionId}`);
      
      return {
        message: `Successfully deleted ${deletedMessages.count} incomplete messages`,
        count: deletedMessages.count,
        streamAborted: wasStreaming,
      };
    } catch (error) {
      this.logger.error(`Error deleting incomplete messages for session ${sessionId}:`, error);
      throw error;
    }
  }

  /**
   * Edit a user message and delete all subsequent messages
   */
  async editMessage(
    userId: string,
    sessionId: string,
    messageId: string,
    newContent: string,
  ): Promise<any> {
    // Make edit + cleanup + placeholder creation atomic
    await this.verifySessionAccess(userId, sessionId);

    const messageToEdit = await this.prisma.chatMessage.findUnique({ where: { id: messageId } });
    if (!messageToEdit) {
      throw new NotFoundException('Message not found');
    }
    if (messageToEdit.sessionId !== sessionId) {
      throw new ForbiddenException('Message does not belong to this session');
    }
    if (messageToEdit.role !== MessageRole.user) {
      throw new BadRequestException('Can only edit user messages');
    }

    const result = await this.prisma.$transaction(async (tx) => {
      // Update the user message content and clear stopped flag
      const updatedMessage = await tx.chatMessage.update({
        where: { id: messageId },
        data: {
          content: newContent,
          isStopped: false,
          stoppedAt: null,
        },
        include: { attachments: true },
      });

      // Delete assistant messages that came after this user message
      await tx.chatMessage.deleteMany({
        where: {
          sessionId,
          role: MessageRole.assistant,
          createdAt: { gt: messageToEdit.createdAt },
        },
      });

      // Create an assistant placeholder message for the upcoming regenerated response
      const assistantPlaceholder = await tx.chatMessage.create({
        data: {
          sessionId,
          role: MessageRole.assistant,
          content: '',
          model: 'gemini-2.5-flash',
          isStopped: false,
        },
      });

      // Update session timestamp
      await tx.chatSession.update({ where: { id: sessionId }, data: { updatedAt: new Date() } });

      return {
        editedMessage: updatedMessage,
        assistantMessageId: assistantPlaceholder.id,
      };
    });

    this.logger.log(`Message ${messageId} edited and subsequent assistant messages deleted; placeholder ${result.assistantMessageId} created`);

    return result;
  }

  /**
   * Map a Prisma ChatMessage record to a plain DTO expected by the API
   */
  private mapPrismaMessageToDTO(message: any) {
    if (!message) return null;

    return {
      id: message.id,
      sessionId: message.sessionId,
      role: message.role,
      content: message.content,
      model: message.model || null,
      promptTokens: message.promptTokens || null,
      completionTokens: message.completionTokens || null,
      cachedTokens: message.cachedTokens || null,
      totalTokens: message.totalTokens || null,
      feedbackRating: message.feedbackRating || null,
      feedbackComment: message.feedbackComment || null,
      createdAt: message.createdAt,
      attachments: (message.attachments || []).map((a: any) => ({
        id: a.id,
        attachmentType: a.attachmentType,
        fileUrl: a.fileUrl,
        fileName: a.fileName || null,
        metadata: a.metadata || null,
        createdAt: a.createdAt,
      })),
    };
  }

  async deleteMessage(userId: string, sessionId: string, messageId: string) {
    // Verify session belongs to user
    const session = await this.prisma.chatSession.findUnique({
      where: { id: sessionId },
      include: { messages: true },
    });

    if (!session) {
      throw new NotFoundException('Chat session not found');
    }

    if (session.userId !== userId) {
      throw new ForbiddenException('You do not have permission to delete messages from this session');
    }

    // Verify message exists and belongs to this session
    const message = await this.prisma.chatMessage.findUnique({
      where: { id: messageId },
    });

    if (!message) {
      throw new NotFoundException('Message not found');
    }

    if (message.sessionId !== sessionId) {
      throw new BadRequestException('Message does not belong to this session');
    }

    // Delete the message (cascade will delete attachments automatically)
    await this.prisma.chatMessage.delete({
      where: { id: messageId },
    });

    return { message: 'Message deleted successfully', messageId };
  }

  /**
   * Save a partial assistant response when streaming is stopped
   * This allows the user to see what was generated and edit/resend if needed
   */
  async savePartialResponse(params: {
    sessionId?: string;
    messageId?: string;
    userId: string;
    partialContent: string;
    tokenUsage: { totalTokens: number };
    stoppedAt: Date;
    durationMs: number;
  }): Promise<{ messageId: string; sessionId?: string }> {
    const { sessionId, messageId, userId, partialContent, tokenUsage, stoppedAt } = params;

    // If we have a messageId, update the existing message
    if (messageId) {
      try {
        await this.prisma.chatMessage.update({
          where: { id: messageId },
          data: {
            content: partialContent,
            isStopped: true,
            stoppedAt,
            totalTokens: tokenUsage.totalTokens,
          },
        });

        // Mark the triggering user message as stopped so edit button shows
        if (sessionId) {
          await this.markLastUserMessageStopped(sessionId);
        }

        return { messageId, sessionId };
      } catch (error) {
        this.logger.error(`Failed to update message ${messageId} with partial content:`, error);
        // Continue to create a new message if update fails
      }
    }

    // Otherwise, create a new assistant message with the partial content
    if (!sessionId) {
      this.logger.warn('Cannot save partial without sessionId');
      return { messageId: '', sessionId: '' };
    }

    const assistantMessage = await this.prisma.chatMessage.create({
      data: {
        sessionId,
        role: MessageRole.assistant,
        content: partialContent,
        model: 'gemini-2.5-flash',
        totalTokens: tokenUsage.totalTokens,
        isStopped: true,
        stoppedAt,
      },
    });

    // Mark the triggering user message as stopped
    await this.markLastUserMessageStopped(sessionId);

    this.logger.log(`Partial response saved for session ${sessionId}: ${assistantMessage.id}`);
    return { messageId: assistantMessage.id, sessionId };
  }

  /**
   * Mark the last user message in a session as stopped
   * This allows the frontend to show an edit button on the user's prompt
   */
  private async markLastUserMessageStopped(sessionId: string): Promise<void> {
    try {
      const lastUserMessage = await this.prisma.chatMessage.findFirst({
        where: {
          sessionId,
          role: MessageRole.user,
        },
        orderBy: {
          createdAt: 'desc',
        },
      });

      if (lastUserMessage) {
        await this.prisma.chatMessage.update({
          where: { id: lastUserMessage.id },
          data: { isStopped: true, stoppedAt: new Date() },
        });
      }
    } catch (error) {
      this.logger.error(`Failed to mark user message as stopped:`, error);
    }
  }

  /**
   * Clean up stopped messages that were not edited
   * Called when the user reloads the page to remove abandoned partial responses
   */
  async cleanupStoppedMessages(userId: string): Promise<{ deletedCount: number; messageIds: string[] }> {
    try {
      // Find all sessions for this user
      const sessions = await this.prisma.chatSession.findMany({
        where: { userId },
        select: { id: true },
      });

      const sessionIds = sessions.map(s => s.id);
      const deletedMessageIds: string[] = [];

      // For each session, find stopped assistant messages and their preceding user messages
      for (const sessionId of sessionIds) {
        const stoppedMessages = await this.prisma.chatMessage.findMany({
          where: {
            sessionId,
            isStopped: true,
            role: MessageRole.assistant,
          },
          orderBy: { createdAt: 'asc' },
        });

        for (const stoppedMsg of stoppedMessages) {
          // Find the user message that triggered this assistant response
          const userMessage = await this.prisma.chatMessage.findFirst({
            where: {
              sessionId,
              role: MessageRole.user,
              createdAt: { lt: stoppedMsg.createdAt },
            },
            orderBy: { createdAt: 'desc' },
          });

          // Delete both the stopped assistant message and the triggering user message
          if (stoppedMsg.id) {
            await this.prisma.chatMessage.delete({ where: { id: stoppedMsg.id } });
            deletedMessageIds.push(stoppedMsg.id);
          }

          if (userMessage?.id && userMessage.isStopped) {
            await this.prisma.chatMessage.delete({ where: { id: userMessage.id } });
            deletedMessageIds.push(userMessage.id);
          }
        }
      }

      this.logger.log(`Cleaned up ${deletedMessageIds.length} stopped messages for user ${userId}`);
      return { deletedCount: deletedMessageIds.length, messageIds: deletedMessageIds };
    } catch (error) {
      this.logger.error('Error cleaning up stopped messages:', error);
      return { deletedCount: 0, messageIds: [] };
    }
  }

  /**
   * ============================================
   * RAG CHAT PIPELINE - NEW METHODS
   * ============================================
   */

  /**
   * Main Pipeline Orchestrator
   *
   * Orchestrates the complete RAG chat pipeline:
   * 1. Store user message
   * 2. Analyze images (if any)
   * 3. Generate embeddings for semantic search
   * 4. Retrieve relevant knowledge chunks via pgvector
   * 5. Prepare conversation context (with summarization)
   * 6. Stream LLM response with context awareness
   * 7. Store assistant response
   * 8. Update context summary incrementally
   *
   * @param userId - Authenticated user ID
   * @param sessionId - Chat session ID
   * @param dto - Pipeline message request with content and images
   * @returns Async generator yielding pipeline chunks for streaming
   */
  async *streamPipelineMessage(
    userId: string,
    sessionId: string,
    dto: PipelineMessageDto,
  ): AsyncGenerator<PipelineChunk> {
    this.logger.debug(`Starting pipeline message for session ${sessionId}`);

    try {
      // Verify session ownership
      const session = await this.prisma.chatSession.findUnique({
        where: { id: sessionId },
      });

      if (!session || session.userId !== userId) {
        throw new ForbiddenException('Not authorized to access this session');
      }

      // Stage 0: Store user message
      const userMessage = await this.storeUserMessage(userId, sessionId, dto);
      this.logger.debug(`User message stored: ${userMessage.id}`);

      // Stage 1: Process images (if any)
      let imageDescriptions = '';
      if (dto.images?.length > 0) {
        try {
          const analyses = await this.openaiVisionService.analyzeAndStoreImages(
            userMessage.id,
            dto.images,
          );
          imageDescriptions = analyses.map((a) => a.description).join('\n');
          yield {
            stage: 'image-analysis',
            metadata: { analyses },
          };
          this.logger.debug(`Analyzed ${analyses.length} images`);
        } catch (error) {
          this.logger.warn(`Image analysis failed, continuing without images: ${error}`);
          // Continue pipeline without image descriptions on non-critical failure
        }
      }

      // Stage 2: Generate embeddings
      const promptWithImages = dto.content + '\n' + imageDescriptions;
      const embedding = await this.openaiEmbeddingService.generate(promptWithImages);
      yield { stage: 'embedding' };
      this.logger.debug(`Embedding generated`);

      // Stage 3: Retrieve knowledge chunks
      const chunks = await this.ragRetrievalService.retrieveTopK(embedding, 10);
      yield {
        stage: 'retrieval',
        metadata: { chunkCount: chunks.length },
      };
      this.logger.debug(`Retrieved ${chunks.length} knowledge chunks`);

      // Fetch session history for context
      const messages = await this.fetchSessionHistory(sessionId);

      // Stage 4: Prepare context (includes summary generation if needed)
      const contextData = await this.contextManagerService.prepareContext(
        sessionId,
        messages,
      );
      this.logger.debug(
        `Context prepared with ${contextData.recentMessages.length} recent messages`,
      );

      // Stage 5: Stream LLM response
      let fullResponse = '';
      let tokenUsage: TokenUsage = {
        promptTokens: 0,
        completionTokens: 0,
        totalTokens: 0,
      };

      for await (const token of this.openaiLLMService.streamCompletion(
        dto.content,
        contextData.summary,
        chunks,
        dto.images || [],
      )) {
        fullResponse += token;
        yield {
          stage: 'llm-generation',
          token,
        };
      }
      this.logger.debug(`LLM streaming completed, response length: ${fullResponse.length}`);

      // Stage 6: Store assistant response
      const assistantMessage = await this.storeAssistantMessage(
        sessionId,
        fullResponse,
        tokenUsage,
      );
      this.logger.debug(`Assistant message stored: ${assistantMessage.id}`);

      // Stage 7: Update context summary if needed
      await this.contextManagerService.updateContextSummary(
        sessionId,
        userMessage,
        assistantMessage,
      );
      this.logger.debug(`Context summary updated`);

      // Final: Complete signal
      yield {
        stage: 'complete',
        messageId: assistantMessage.id,
      };
    } catch (error) {
      this.logger.error(`Pipeline error: ${error.message}`, error.stack);
      yield {
        stage: 'error',
        errorMessage: error.message,
      };
    }
  }

  /**
   * Helper: Store user message in database
   * Creates ChatMessage record with optional image attachments
   *
   * Uses Prisma transactions for atomicity + retry logic for transient DB errors
   *
   * @param userId - User ID
   * @param sessionId - Chat session ID
   * @param dto - Pipeline message with content and images
   * @returns Created ChatMessage with attachments
   */
  private async storeUserMessage(
    userId: string,
    sessionId: string,
    dto: PipelineMessageDto,
  ): Promise<ChatMessage> {
    this.logger.debug(
      `Storing user message for session ${sessionId}, ${dto.images?.length || 0} images`,
    );

    return this.retryAsync(async () => {
      return await this.prisma.$transaction(async (tx) => {
        // Create user message
        const userMessage = await tx.chatMessage.create({
          data: {
            sessionId,
            role: MessageRole.user,
            content: dto.content,
          },
        });

        // Upload and attach images if present
        if (dto.images && dto.images.length > 0) {
          for (const imageData of dto.images) {
            try {
              // Upload image to Vercel Blob
              const fileUrl =
                await this.vercelBlobService.uploadBase64Image(imageData);

              // Create attachment record
              await tx.messageAttachment.create({
                data: {
                  messageId: userMessage.id,
                  attachmentType: AttachmentType.image,
                  fileUrl,
                },
              });
            } catch (error) {
              this.logger.warn(
                `Failed to upload image, continuing without attachment: ${error.message}`,
              );
              // Continue without this image - non-critical failure
            }
          }
        }

        this.logger.debug(`✅ User message stored: ${userMessage.id}`);
        return userMessage;
      });
    });
  }

  /**
   * Helper: Fetch conversation history
   * Retrieves all messages in a session in chronological order
   *
   * Wrapped in retry logic for transient DB errors
   *
   * @param sessionId - Chat session ID
   * @returns Array of ChatMessage objects with attachments
   */
  private async fetchSessionHistory(
    sessionId: string,
  ): Promise<ChatMessage[]> {
    this.logger.debug(`Fetching history for session ${sessionId}`);

    return this.retryAsync(async () => {
      const messages = await this.prisma.chatMessage.findMany({
        where: { sessionId },
        include: {
          attachments: true,
        },
        orderBy: { createdAt: 'asc' },
      });

      this.logger.debug(`✅ Fetched ${messages.length} messages from history`);
      return messages;
    });
  }

  /**
   * Helper: Store assistant response in database
   * Creates ChatMessage record with token usage tracking
   *
   * Updates session timestamp and tracks token consumption for billing
   *
   * @param sessionId - Chat session ID
   * @param content - LLM response text
   * @param tokenUsage - Token usage statistics
   * @returns Created ChatMessage with token data
   */
  private async storeAssistantMessage(
    sessionId: string,
    content: string,
    tokenUsage: TokenUsage,
  ): Promise<ChatMessage> {
    this.logger.debug(
      `Storing assistant message for session ${sessionId}, tokens: ${tokenUsage.totalTokens}`,
    );

    return this.retryAsync(async () => {
      return await this.prisma.$transaction(async (tx) => {
        // Create assistant message with token tracking
        const assistantMessage = await tx.chatMessage.create({
          data: {
            sessionId,
            role: MessageRole.assistant,
            content,
            promptTokens: tokenUsage.promptTokens,
            completionTokens: tokenUsage.completionTokens,
            totalTokens: tokenUsage.totalTokens,
            cachedTokens: tokenUsage.cachedTokens || 0,
          },
        });

        // Update session timestamp to mark last activity
        await tx.chatSession.update({
          where: { id: sessionId },
          data: { updatedAt: new Date() },
        });

        this.logger.debug(
          `✅ Assistant message stored: ${assistantMessage.id} (${tokenUsage.totalTokens} tokens)`,
        );
        return assistantMessage;
      });
    });
  }
}
