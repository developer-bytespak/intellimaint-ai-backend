import { Injectable, NotFoundException, ForbiddenException, BadRequestException } from '@nestjs/common';
import { PrismaService } from 'prisma/prisma.service';
import { UpdateSessionDto } from '../dto/update-session.dto';
import { CreateMessageDto } from '../dto/create-message.dto';
import { ListSessionsQueryDto } from '../dto/list-sessions-query.dto';
import { ChatSessionStatus, MessageRole, AttachmentType } from '@prisma/client';

@Injectable()
export class ChatService {
  constructor(private prisma: PrismaService) {}

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
            select: {
              id: true,
              content: true,
              role: true,
              createdAt: true,
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
    // Verify access (will throw if not found or wrong owner)
    const session = await this.verifySessionAccess(userId, sessionId);

    // Create the message
    // Only images are allowed as attachments
    const message = await this.prisma.chatMessage.create({
      data: {
        sessionId,
        role: MessageRole.user,
        content: dto.content,
        attachments: {
          create: [
            // Create image attachments only
            ...(dto.images?.map((imageUrl) => ({
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

    // Update session's updatedAt timestamp
    await this.prisma.chatSession.update({
      where: { id: sessionId },
      data: {
        updatedAt: new Date(),
        // Auto-generate title from first message if title is null
        ...(session.title === null && {
          title: dto.content.length > 50 ? dto.content.substring(0, 50) + '...' : dto.content,
        }),
      },
    });

    return message;
  }

  async createMessageWithSession(userId: string, dto: CreateMessageDto) {
    // Create session first if it doesn't exist
    const session = await this.prisma.chatSession.create({
      data: {
        userId,
        title: null, // Will be set from first message
        equipmentContext: [],
        status: ChatSessionStatus.active,
      },
    });

    // Create the message
    const message = await this.prisma.chatMessage.create({
      data: {
        sessionId: session.id,
        role: MessageRole.user,
        content: dto.content,
        attachments: {
          create: [
            // Create image attachments only
            ...(dto.images?.map((imageUrl) => ({
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

    // Update session's updatedAt timestamp and set title from first message
    const updatedSession = await this.prisma.chatSession.update({
      where: { id: session.id },
      data: {
        updatedAt: new Date(),
        title: dto.content.length > 50 ? dto.content.substring(0, 50) + '...' : dto.content,
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
      message,
    };
  }
}
