import {
  Controller,
  Post,
  Get,
  Put,
  Delete,
  Param,
  Body,
  Query,
  Req,
  UseGuards,
  Res,
  Sse,
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

  @Post('sessions/:sessionId/messages/stream')
  async streamMessage(
    @Req() req: any,
    @Param('sessionId') sessionId: string,
    @Body() body: any,
    @Res() res: Response,
  ) {
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

      // Stream tokens as they arrive
      try {
        for await (const chunk of this.chatService.streamMessage(userId, sessionId, createDto)) {
          res.write(`data: ${JSON.stringify(chunk)}\n\n`);
        }
        res.end();
      } catch (streamError) {
        console.error('Error in stream:', streamError);
        res.write(`data: ${JSON.stringify({ error: streamError.message, done: true })}\n\n`);
        res.end();
      }
    } catch (error) {
      console.error('Error starting stream:', error);
      if (!res.headersSent) {
        res.status(error.status || 500).json({
          statusCode: error.status || 500,
          message: error.message || 'Internal server error',
        });
      } else {
        res.write(`data: ${JSON.stringify({ error: error.message, done: true })}\n\n`);
        res.end();
      }
    }
  }

  @Post('messages/stream')
  async streamMessageWithSession(
    @Req() req: any,
    @Body() body: any,
    @Res() res: Response,
  ) {
    try {
      const userId = req.user.id;
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

      // Set SSE headers
      res.setHeader('Content-Type', 'text/event-stream');
      res.setHeader('Cache-Control', 'no-cache');
      res.setHeader('Connection', 'keep-alive');
      res.setHeader('X-Accel-Buffering', 'no');

      // Stream tokens as they arrive
      try {
        for await (const chunk of this.chatService.streamMessageWithSession(userId, createDto)) {
          res.write(`data: ${JSON.stringify(chunk)}\n\n`);
        }
        res.end();
      } catch (streamError) {
        console.error('Error in stream:', streamError);
        res.write(`data: ${JSON.stringify({ error: streamError.message, done: true })}\n\n`);
        res.end();
      }
    } catch (error) {
      console.error('Error starting stream:', error);
      if (!res.headersSent) {
        res.status(error.status || 500).json({
          statusCode: error.status || 500,
          message: error.message || 'Internal server error',
        });
      } else {
        res.write(`data: ${JSON.stringify({ error: error.message, done: true })}\n\n`);
        res.end();
      }
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
