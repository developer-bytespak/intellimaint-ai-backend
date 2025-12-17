import {
  Controller,
  Post,
  Get,
  Put,
  Patch,
  Delete,
  Param,
  Body,
  Query,
  Req,
  UseGuards,
  Res,
  Sse,
  Logger,
} from '@nestjs/common';
import { ChatService } from '../services/chat.service';
import { JwtAuthGuard } from '../../auth/jwt-auth.guard';
import { UpdateSessionDto } from '../dto/update-session.dto';
import { CreateMessageDto } from '../dto/create-message.dto';
import { ListSessionsQueryDto } from '../dto/list-sessions-query.dto';
import { nestResponse, nestError } from 'src/common/helpers/responseHelpers';
import { plainToInstance } from 'class-transformer';
import { validate } from 'class-validator';
import type { Response } from 'express';

@Controller('chat')
@UseGuards(JwtAuthGuard)
export class ChatController {
  private readonly logger = new Logger(ChatController.name);

  constructor(private chatService: ChatService) {}

  @Get('sessions')
  async listSessions(
    @Req() req: any,
    @Query() query: ListSessionsQueryDto,
    @Res({ passthrough: true }) res: Response,
  ) {
    try {
      const userId = req.user.id;
      const queryDto = plainToInstance(ListSessionsQueryDto, query);
      const errors = await validate(queryDto);

      if (errors.length > 0) {
        const messages = errors.map((err) => Object.values(err.constraints || {})).flat();
        return nestError(400, 'Validation failed', messages)(res);
      }

      const result = await this.chatService.listSessions(userId, queryDto);
      return nestResponse(200, 'Chat sessions retrieved successfully', result)(res);
    } catch (error) {
      console.error('Error listing chat sessions:', error);
      return nestError(500, 'Failed to retrieve chat sessions', error.message || 'Internal server error')(
        res,
      );
    }
  }

  @Get('sessions/:sessionId')
  async getSession(
    @Req() req: any,
    @Param('sessionId') sessionId: string,
    @Res({ passthrough: true }) res: Response,
  ) {
    try {
      const userId = req.user.id;
      const session = await this.chatService.getSession(userId, sessionId);
      return nestResponse(200, 'Chat session retrieved successfully', session)(res);
    } catch (error) {
      if (error.status === 404) {
        return nestError(404, error.message)(res);
      }
      if (error.status === 403) {
        return nestError(403, error.message)(res);
      }
      console.error('Error retrieving chat session:', error);
      return nestError(500, 'Failed to retrieve chat session', error.message || 'Internal server error')(
        res,
      );
    }
  }

  @Put('sessions/:sessionId')
  async updateSession(
    @Req() req: any,
    @Param('sessionId') sessionId: string,
    @Body() body: any,
    @Res({ passthrough: true }) res: Response,
  ) {
    try {
      const userId = req.user.id;
      const updateDto = plainToInstance(UpdateSessionDto, body);
      const errors = await validate(updateDto);

      if (errors.length > 0) {
        const messages = errors.map((err) => Object.values(err.constraints || {})).flat();
        return nestError(400, 'Validation failed', messages)(res);
      }

      const session = await this.chatService.updateSession(userId, sessionId, updateDto);
      return nestResponse(200, 'Chat session updated successfully', session)(res);
    } catch (error) {
      if (error.status === 404) {
        return nestError(404, error.message)(res);
      }
      if (error.status === 403) {
        return nestError(403, error.message)(res);
      }
      console.error('Error updating chat session:', error);
      return nestError(500, 'Failed to update chat session', error.message || 'Internal server error')(
        res,
      );
    }
  }

  @Delete('sessions/:sessionId')
  async deleteSession(
    @Req() req: any,
    @Param('sessionId') sessionId: string,
    @Res({ passthrough: true }) res: Response,
  ) {
    try {
      const userId = req.user.id;
      const result = await this.chatService.deleteSession(userId, sessionId);
      return nestResponse(200, result.message, result)(res);
    } catch (error) {
      if (error.status === 404) {
        return nestError(404, error.message)(res);
      }
      if (error.status === 403) {
        return nestError(403, error.message)(res);
      }
      console.error('Error deleting chat session:', error);
      return nestError(500, 'Failed to delete chat session', error.message || 'Internal server error')(
        res,
      );
    }
  }

  @Post('cleanup-stopped')
  async cleanupStoppedMessages(
    @Req() req: any,
    @Res({ passthrough: true }) res: Response,
  ) {
    try {
      const userId = req.user.id;
      const result = await this.chatService.cleanupStoppedMessages(userId);
      return nestResponse(200, 'Stopped messages cleaned up successfully', result)(res);
    } catch (error) {
      this.logger.error('Error cleaning up stopped messages:', error);
      return nestError(500, 'Failed to cleanup stopped messages', error.message || 'Internal server error')(res);
    }
  }

  @Post('messages')
  async createMessageWithSession(
    @Req() req: any,
    @Body() body: any,
    @Res({ passthrough: true }) res: Response,
  ) {
    try {
      const userId = req.user.id;
      const createDto = plainToInstance(CreateMessageDto, body);
      const errors = await validate(createDto);

      if (errors.length > 0) {
        const messages = errors.map((err) => Object.values(err.constraints || {})).flat();
        console.error('Validation errors:', messages);
        console.error('Request body:', body);
        return nestError(400, 'Validation failed', messages)(res);
      }

      // Additional validation: must have either content or images
      const hasContent = createDto.content && createDto.content.trim().length > 0;
      const hasImages = createDto.images && createDto.images.length > 0;
      
      if (!hasContent && !hasImages) {
        console.error('Validation failed: No content or images provided');
        console.error('DTO received:', JSON.stringify(createDto, null, 2));
        return nestError(400, 'Message must have either content or images')(res);
      }

      const result = await this.chatService.createMessageWithSession(userId, createDto);
      return nestResponse(201, 'Message and session created successfully', result)(res);
    } catch (error) {
      console.error('Error creating message with session:', error);
      console.error('Error stack:', error.stack);
      console.error('Error details:', {
        message: error.message,
        name: error.name,
        status: error.status,
      });
      return nestError(
        error.status || 500,
        'Failed to create message',
        error.message || 'Internal server error',
      )(res);
    }
  }

  @Post('sessions/:sessionId/messages')
  async createMessage(
    @Req() req: any,
    @Param('sessionId') sessionId: string,
    @Body() body: any,
    @Res({ passthrough: true }) res: Response,
  ) {
    try {
      const userId = req.user.id;
      const createDto = plainToInstance(CreateMessageDto, body);
      const errors = await validate(createDto);

      if (errors.length > 0) {
        const messages = errors.map((err) => Object.values(err.constraints || {})).flat();
        return nestError(400, 'Validation failed', messages)(res);
      }

      const message = await this.chatService.createMessage(userId, sessionId, createDto);
      return nestResponse(201, 'Message created successfully', message)(res);
    } catch (error) {
      if (error.status === 404) {
        return nestError(404, error.message)(res);
      }
      if (error.status === 403) {
        return nestError(403, error.message)(res);
      }
      console.error('Error creating message:', error);
      return nestError(500, 'Failed to create message', error.message || 'Internal server error')(res);
    }
  }

  // ============================================================================
  // SSE ENDPOINTS - COMMENTED OUT (Migrated to Socket.IO)
  // ============================================================================
  // These endpoints have been replaced by Socket.IO streaming via SocketChatGateway
  // Socket.IO provides better bidirectional communication and instant abort support
  // See: gateway/src/modules/chat/gateway/socket-chat.gateway.ts
  // ============================================================================

  /*
  @Post('sessions/:sessionId/messages/stream')
  async streamMessage(
    @Req() req: any,
    @Param('sessionId') sessionId: string,
    @Body() body: any,
    @Res() res: Response,
  ) {
    // Generate unique request ID for this SSE stream
    const requestId = `${sessionId}-${Date.now()}-${Math.random()}`;
    const abortController = new AbortController();
    
    try {
      const userId = req.user.id;
      const createDto = plainToInstance(CreateMessageDto, body);
      const errors = await validate(createDto);

      if (errors.length > 0) {
        const messages = errors.map((err) => Object.values(err.constraints || {})).flat();
        res.status(400).json({ statusCode: 400, message: 'Validation failed', data: messages });
        return;
      }

      // Set SSE headers
      res.setHeader('Content-Type', 'text/event-stream');
      res.setHeader('Cache-Control', 'no-cache');
      res.setHeader('Connection', 'keep-alive');
      res.setHeader('X-Accel-Buffering', 'no'); // Disable nginx buffering

      // ⭐ CRITICAL: Detect client disconnect
      // When client closes connection, this fires immediately
      req.on('close', () => {
        console.log(`Client disconnected for request ${requestId}`);
        // Mark this request as aborted so backend stops processing
        this.chatService.abortRequest(requestId);
      });

      // Register the request so it can be tracked
      this.chatService.registerRequest(requestId, abortController);

      // Stream tokens as they arrive
      try {
        for await (const chunk of this.chatService.streamMessage(userId, sessionId, createDto, requestId)) {
          // Only write if client is still connected
          if (req.writableEnded) {
            break;
          }
          
          // Don't send event if this was an aborted request
          if (chunk.aborted) {
            console.log(`Skipping send for aborted request ${requestId}`);
            break;
          }
          
          res.write(`data: ${JSON.stringify(chunk)}\n\n`);
        }
        
        // Only end response if still writable
        if (!req.writableEnded) {
          res.end();
        }
      } catch (streamError) {
        console.error('Error in stream:', streamError);
        if (!req.writableEnded) {
          const errorMessage = streamError?.message || 'Stream error occurred';
          res.write(`data: ${JSON.stringify({ error: errorMessage, done: true })}\n\n`);
          res.end();
        }
      }
    } catch (error) {
      console.error('Error starting stream:', error);
      if (!res.headersSent) {
        const errorMessage = error?.message || 'Internal server error';
        const statusCode = error?.status || 500;
        res.status(statusCode).json({
          statusCode,
          message: errorMessage,
        });
      } else if (!req.writableEnded) {
        const errorMessage = error?.message || 'Internal server error';
        res.write(`data: ${JSON.stringify({ error: errorMessage, done: true })}\n\n`);
        res.end();
      }
    } finally {
      // Always clean up the request from tracking
      this.chatService.unregisterRequest(requestId);
    }
  }
  */

  /*
  /*
  @Post('messages/stream')
  async streamMessageWithSession(
    @Req() req: any,
    @Body() body: any,
    @Res() res: Response,
  ) {
    try {
      const userId = req.user.id;
      if (!userId) {
        res.status(401).json({ statusCode: 401, message: 'Unauthorized' });
        return;
      }

      const createDto = plainToInstance(CreateMessageDto, body);
      const errors = await validate(createDto);

      if (errors.length > 0) {
        const messages = errors.map((err) => Object.values(err.constraints || {})).flat();
        res.status(400).json({ statusCode: 400, message: 'Validation failed', data: messages });
        return;
      }

      // Additional validation
      const hasContent = createDto.content && createDto.content.trim().length > 0;
      const hasImages = createDto.images && createDto.images.length > 0;
      
      if (!hasContent && !hasImages) {
        res.status(400).json({ statusCode: 400, message: 'Message must have either content or images' });
        return;
      }

      // Generate unique request ID
      const requestId = `new-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const abortController = new AbortController();

      // Set SSE headers
      res.setHeader('Content-Type', 'text/event-stream');
      res.setHeader('Cache-Control', 'no-cache');
      res.setHeader('Connection', 'keep-alive');
      res.setHeader('X-Accel-Buffering', 'no');

      // Register request for lifecycle tracking
      this.chatService.registerRequest(requestId, abortController);

      // Detect client disconnect
      req.on('close', () => {
        this.logger.log(`Client disconnected from new session stream (request ${requestId})`);
        this.chatService.abortRequest(requestId);
      });

      // Stream tokens as they arrive
      try {
        for await (const chunk of this.chatService.streamMessageWithSession(userId, createDto, requestId)) {
          // Skip writing if client already disconnected
          if (req.writableEnded) {
            break;
          }
          // Skip events for aborted streams
          if (chunk.aborted) {
            this.logger.log(`Skipping write for aborted stream (request ${requestId})`);
            break;
          }
          res.write(`data: ${JSON.stringify(chunk)}\n\n`);
        }
        res.end();
      } catch (streamError) {
        this.logger.error(`Error in new session stream (request ${requestId}):`, streamError);
        if (!req.writableEnded) {
          const errorMessage = streamError?.message || 'Stream error occurred';
          res.write(`data: ${JSON.stringify({ error: errorMessage, done: true })}\n\n`);
          res.end();
        }
      } finally {
        this.chatService.unregisterRequest(requestId);
      }
    } catch (error) {
      this.logger.error('Error starting new session stream:', error);
      if (!res.headersSent) {
        const errorMessage = error?.message || 'Internal server error';
        const statusCode = error?.status || 500;
        res.status(statusCode).json({
          statusCode,
          message: errorMessage,
        });
      } else {
        const errorMessage = error?.message || 'Internal server error';
        res.write(`data: ${JSON.stringify({ error: errorMessage, done: true })}\n\n`);
        res.end();
      }
    }
  }
  */

  // ============================================================================
  // END SSE ENDPOINTS
  // ============================================================================

  @Post('sessions/:sessionId/stop-stream')
  async stopStreamPost(
    @Req() req: any,
    @Param('sessionId') sessionId: string,
    @Res({ passthrough: true }) res: Response,
  ) {
    return this.stopStreamHandler(req, sessionId, res);
  }

  @Delete('sessions/:sessionId/stop-stream')
  async stopStream(
    @Req() req: any,
    @Param('sessionId') sessionId: string,
    @Res({ passthrough: true }) res: Response,
  ) {
    return this.stopStreamHandler(req, sessionId, res);
  }

  private async stopStreamHandler(
    req: any,
    sessionId: string,
    res: Response,
  ) {
    try {
      // Extract userId with multiple fallbacks
      const userId = req.user?.id || req.user?.userId || req.user?.sub;
      
      if (!userId) {
        this.logger.error('User not found in request');
        return nestError(401, 'Unauthorized')(res);
      }

      // Abort the stream and cleanup
      const result = await this.chatService.stopStream(userId, sessionId);
      
      // Return a safe JSON response without circular references
      return res.status(200).json({
        statusCode: 200,
        message: 'Stream stopped successfully',
        data: {
          requestsAborted: Number(result.requestsAborted) || 0,
          geminiAborted: Boolean(result.geminiAborted),
          message: result.message || 'Stream stopped',
        },
      });
    } catch (error) {
      this.logger.error('Error stopping stream:', error);
      
      const statusCode = error?.status || 500;
      const errorMessage = error?.message || 'Failed to stop stream';
      
      if (error.status === 404) {
        return nestError(404, errorMessage)(res);
      }
      if (error.status === 403) {
        return nestError(403, errorMessage)(res);
      }
      if (error.status === 401) {
        return nestError(401, 'Unauthorized')(res);
      }
      
      return res.status(statusCode).json({
        statusCode,
        message: errorMessage,
        data: null,
      });
    }
  }

  @Patch('sessions/:sessionId/messages/:messageId')
  async editMessage(
    @Req() req: any,
    @Param('sessionId') sessionId: string,
    @Param('messageId') messageId: string,
    @Body() body: { content: string },
    @Res({ passthrough: true }) res: Response,
  ) {
    try {
      const userId = req.user.id;

      if (!body.content || body.content.trim() === '') {
        return nestError(400, 'Message content cannot be empty')(res);
      }

      const updatedMessage = await this.chatService.editMessage(
        userId,
        sessionId,
        messageId,
        body.content.trim(),
      );
      return nestResponse(200, 'Message edited successfully', updatedMessage)(res);
    } catch (error) {
      if (error.status === 404) {
        return nestError(404, error.message)(res);
      }
      if (error.status === 403) {
        return nestError(403, error.message)(res);
      }
      if (error.status === 400) {
        return nestError(400, error.message)(res);
      }
      console.error('Error editing message:', error);
      return nestError(500, 'Failed to edit message', error.message || 'Internal server error')(res);
    }
  }

  @Delete('sessions/:sessionId/messages/:messageId')
  async deleteMessage(
    @Req() req: any,
    @Param('sessionId') sessionId: string,
    @Param('messageId') messageId: string,
    @Res({ passthrough: true }) res: Response,
  ) {
    try {
      const userId = req.user.id;
      const result = await this.chatService.deleteMessage(userId, sessionId, messageId);
      return nestResponse(200, 'Message deleted successfully', result)(res);
    } catch (error) {
      if (error.status === 404) {
        return nestError(404, error.message)(res);
      }
      if (error.status === 403) {
        return nestError(403, error.message)(res);
      }
      if (error.status === 400) {
        return nestError(400, error.message)(res);
      }
      console.error('Error deleting message:', error);
      return nestError(500, 'Failed to delete message', error.message || 'Internal server error')(res);
    }
  }
}
