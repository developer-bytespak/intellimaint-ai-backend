import { Injectable, NotFoundException, ForbiddenException, BadRequestException, Logger } from '@nestjs/common';
import { PrismaService } from 'prisma/prisma.service';
import { UpdateSessionDto } from '../dto/update-session.dto';
import { CreateMessageDto } from '../dto/create-message.dto';
import { ListSessionsQueryDto } from '../dto/list-sessions-query.dto';
import { ChatSessionStatus, MessageRole, AttachmentType } from '@prisma/client';
import { GeminiChatService } from './gemini-chat.service';
import { ImageUtilService } from './image-util.service';
import { VercelBlobService } from './vercel-blob.service';

@Injectable()
export class ChatService {
  private readonly logger = new Logger(ChatService.name);

  constructor(
    private prisma: PrismaService,
    private geminiChatService: GeminiChatService,
    private imageUtilService: ImageUtilService,
    private vercelBlobService: VercelBlobService,
  ) {}

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
   */
  async *streamMessage(
    userId: string,
    sessionId: string,
    dto: CreateMessageDto,
  ): AsyncGenerator<{ token: string; done: boolean; fullText?: string; messageId?: string; tokenUsage?: any }> {
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

    try {
      // Stream tokens from Gemini
      for await (const chunk of this.geminiChatService.streamChatResponse(
        sessionId,
        prompt,
        messages,
        imageDataList.length > 0 ? imageDataList : undefined,
        contextSummary,
      )) {
        if (chunk.done) {
          // Final chunk - create assistant message in database
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
          // Yield token chunk
          yield {
            token: chunk.token,
            done: false,
            fullText: chunk.fullText,
          };
        }
      }
    } catch (error) {
      this.logger.error('Error streaming message:', error);
      throw error;
    }
  }

  /**
   * Stream message creation with new session (for first message)
   */
  async *streamMessageWithSession(
    userId: string,
    dto: CreateMessageDto,
  ): AsyncGenerator<{ token: string; done: boolean; fullText?: string; sessionId?: string; messageId?: string; tokenUsage?: any }> {
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

    try {
      for await (const chunk of this.geminiChatService.streamChatResponse(
        session.id,
        prompt,
        [],
        imageDataList.length > 0 ? imageDataList : undefined,
        null,
      )) {
        if (chunk.done) {
          finalFullText = chunk.fullText || '';
          finalTokenUsage = chunk.tokenUsage;
          
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
          yield {
            token: chunk.token,
            done: false,
            fullText: chunk.fullText,
            sessionId: session.id,
          };
        }
      }
    } catch (error) {
      this.logger.error('Error streaming message with session:', error);
      throw error;
    }
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
}
