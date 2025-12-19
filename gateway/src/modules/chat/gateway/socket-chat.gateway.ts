import {
  WebSocketGateway,
  WebSocketServer,
  SubscribeMessage,
  OnGatewayConnection,
  OnGatewayDisconnect,
  ConnectedSocket,
  MessageBody,
} from '@nestjs/websockets';
import { Server, Socket } from 'socket.io';
import { Logger } from '@nestjs/common';
import { ChatService } from '../services/chat.service';

interface StreamMessagePayload {
  sessionId?: string;
  content: string;
  images?: string[];
  userId: string;
}

@WebSocketGateway({
  cors: {
    origin: [
      'http://localhost:3001', 
      'http://localhost:3000',
      process.env.FRONTEND_URL || 'http://localhost:3001',
      'https://intellimaint-ai.vercel.app',
    ],
    credentials: true,
  },
  namespace: '/chat',
  transports: ['websocket', 'polling'],
})
export class SocketChatGateway implements OnGatewayConnection, OnGatewayDisconnect {
  @WebSocketServer()
  server: Server;

  private readonly logger = new Logger(SocketChatGateway.name);
  private activeStreams = new Map<string, {
    controller: AbortController;
    buffer: string;
    tokenCount: number;
    sessionId?: string;
    messageId?: string;
    startTime: number;
  }>();

  constructor(private chatService: ChatService) {}

  handleConnection(client: Socket) {
    this.logger.log(`✅ Client connected: ${client.id} from ${client.handshake.address}`);
    client.emit('connected', { socketId: client.id, timestamp: new Date().toISOString() });
  }

  handleDisconnect(client: Socket) {
    this.stopStreamForSocket(client.id);
    this.logger.log(`❌ Client disconnected: ${client.id}`);
  }

  /**
   * Stream message with existing session
   */
  @SubscribeMessage('stream-message')
  async handleStreamMessage(
    @ConnectedSocket() client: Socket,
    @MessageBody() payload: StreamMessagePayload,
  ) {
    this.logger.log(`📨 [stream-message] Received from ${client.id}`);
    this.logger.log(`📦 Payload: ${JSON.stringify({
      sessionId: payload.sessionId,
      contentLength: payload.content?.length,
      imagesCount: payload.images?.length,
      userId: payload.userId,
    })}`);

    client.emit('server-ack', { 
      event: 'stream-message', 
      received: true,
      timestamp: new Date().toISOString()
    });

    const { sessionId, content, images, userId } = payload;

    if (!sessionId) {
      this.logger.error('❌ Missing sessionId');
      client.emit('message-error', { error: 'Session ID is required' });
      return;
    }

    if (!userId) {
      this.logger.error('❌ Missing userId');
      client.emit('message-error', { error: 'Unauthorized - userId required' });
      return;
    }

    if ((!content || content.trim() === '') && (!images || images.length === 0)) {
      this.logger.error('❌ Empty content and no images');
      client.emit('message-error', { error: 'Message content or images are required' });
      return;
    }

    const startTime = Date.now();
    const abortController = new AbortController();
    const streamMeta = {
      controller: abortController,
      buffer: '',
      tokenCount: 0,
      sessionId,
      messageId: undefined as string | undefined,
      startTime,
    };
    this.activeStreams.set(client.id, streamMeta);
    const requestId = `socket-${client.id}-${Date.now()}`;

    try {
      this.logger.log(`🚀 Starting stream for session ${sessionId}`);
      this.chatService.registerRequest(requestId, abortController);

      for await (const chunk of this.chatService.streamMessage(
        userId,
        sessionId,
        { content, images: images || [] },
        requestId,
      )) {
        if (abortController.signal.aborted) {
          this.logger.log(`⏹️ Stream aborted for ${client.id}`);
          const duration = Date.now() - startTime;
          this.logger.log(`⏱️ Stream duration: ${duration}ms, Tokens: ${streamMeta.tokenCount}`);
          
          // Persist partial response to database
          try {
            const result = await this.chatService.savePartialResponse({
              sessionId,
              messageId: streamMeta.messageId,
              userId,
              partialContent: streamMeta.buffer,
              tokenUsage: { totalTokens: streamMeta.tokenCount },
              stoppedAt: new Date(),
              durationMs: duration,
            });
            streamMeta.messageId = result.messageId;
            this.logger.log(`✅ Partial response persisted: ${result.messageId}`);
          } catch (error) {
            this.logger.error('❌ Failed to persist partial response:', error);
          }
          
          // Emit partial content as a stopped message
          client.emit('message-chunk', {
            done: true,
            stopped: true,
            partialContent: streamMeta.buffer,
            messageId: streamMeta.messageId,
            tokenUsage: { totalTokens: streamMeta.tokenCount },
          });
          break;
        }

        if (chunk.aborted) {
          const duration = Date.now() - startTime;
          this.logger.log(`⏱️ Stream aborted. Duration: ${duration}ms, Tokens: ${streamMeta.tokenCount}`);
          client.emit('message-chunk', {
            done: true,
            stopped: true,
            partialContent: streamMeta.buffer,
            messageId: streamMeta.messageId,
            tokenUsage: { totalTokens: streamMeta.tokenCount },
          });
          break;
        } else if (chunk.done) {
          const duration = Date.now() - startTime;
          this.logger.log(`✅ Stream completed. Duration: ${duration}ms, Tokens: ${streamMeta.tokenCount}`);
          streamMeta.messageId = chunk.messageId;
          client.emit('message-chunk', {
            done: true,
            messageId: chunk.messageId,
            tokenUsage: chunk.tokenUsage,
          });
          break;
        } else {
          streamMeta.tokenCount++;
          streamMeta.buffer += chunk.token || '';
          if (chunk.messageId) {
            streamMeta.messageId = chunk.messageId;
          }
          client.emit('message-chunk', {
            token: chunk.token,
            done: false,
          });
        }
      }
    } catch (error) {
      this.logger.error(`❌ Stream error for ${client.id}:`, error.stack || error);

      if (error.name === 'AbortError' || abortController.signal.aborted) {
        client.emit('message-stopped', { reason: 'Stream aborted' });
      } else {
        client.emit('message-error', {
          error: error.message || 'Stream error occurred'
        });
      }
    } finally {
      this.chatService.unregisterRequest(requestId);
      this.activeStreams.delete(client.id);
      this.logger.log(`🧹 Cleanup completed for ${client.id}`);
    }
  }

  /**
   * Stream message with new session creation
   */
  @SubscribeMessage('stream-message-new')
  async handleStreamMessageNew(
    @ConnectedSocket() client: Socket,
    @MessageBody() payload: StreamMessagePayload,
  ) {
    this.logger.log(`📨 [stream-message-new] Received from ${client.id}`);
    this.logger.log(`📦 Payload: ${JSON.stringify({
      contentLength: payload.content?.length,
      imagesCount: payload.images?.length,
      userId: payload.userId,
    })}`);

    client.emit('server-ack', { 
      event: 'stream-message-new', 
      received: true,
      timestamp: new Date().toISOString()
    });

    const { content, images, userId } = payload;

    if (!userId) {
      this.logger.error('❌ Missing userId');
      client.emit('message-error', { error: 'Unauthorized - userId required' });
      return;
    }

    if ((!content || content.trim() === '') && (!images || images.length === 0)) {
      this.logger.error('❌ Empty content and no images');
      client.emit('message-error', { error: 'Message content or images are required' });
      return;
    }

    const startTime = Date.now();
    const abortController = new AbortController();
    const streamMeta = {
      controller: abortController,
      buffer: '',
      tokenCount: 0,
      sessionId: undefined as string | undefined,
      messageId: undefined as string | undefined,
      startTime,
    };
    this.activeStreams.set(client.id, streamMeta);
    const requestId = `socket-new-${client.id}-${Date.now()}`;

    try {
      this.logger.log(`🚀 Starting new session stream`);
      this.chatService.registerRequest(requestId, abortController);

      for await (const chunk of this.chatService.streamMessageWithSession(
        userId,
        { content, images: images || [] },
        requestId,
      )) {
        if (abortController.signal.aborted) {
          this.logger.log(`⏹️ Stream aborted for ${client.id}`);
          const duration = Date.now() - startTime;
          this.logger.log(`⏱️ Stream duration: ${duration}ms, Tokens: ${streamMeta.tokenCount}`);
          
          // Persist partial response to database
          try {
            const result = await this.chatService.savePartialResponse({
              sessionId: streamMeta.sessionId,
              messageId: streamMeta.messageId,
              userId,
              partialContent: streamMeta.buffer,
              tokenUsage: { totalTokens: streamMeta.tokenCount },
              stoppedAt: new Date(),
              durationMs: duration,
            });
            streamMeta.sessionId = result.sessionId;
            streamMeta.messageId = result.messageId;
            this.logger.log(`✅ Partial response persisted: ${result.messageId}`);
          } catch (error) {
            this.logger.error('❌ Failed to persist partial response:', error);
          }
          
          // Emit partial content as a stopped message
          client.emit('message-chunk', {
            done: true,
            stopped: true,
            partialContent: streamMeta.buffer,
            sessionId: streamMeta.sessionId,
            messageId: streamMeta.messageId,
            tokenUsage: { totalTokens: streamMeta.tokenCount },
          });
          break;
        }

        if (chunk.aborted) {
          const duration = Date.now() - startTime;
          this.logger.log(`⏱️ Stream aborted. Duration: ${duration}ms, Tokens: ${streamMeta.tokenCount}`);
          client.emit('message-chunk', {
            done: true,
            stopped: true,
            partialContent: streamMeta.buffer,
            sessionId: streamMeta.sessionId,
            messageId: streamMeta.messageId,
            tokenUsage: { totalTokens: streamMeta.tokenCount },
          });
          break;
        } else if (chunk.done) {
          const duration = Date.now() - startTime;
          this.logger.log(`✅ New session created. Session ID: ${chunk.sessionId}, Duration: ${duration}ms, Tokens: ${streamMeta.tokenCount}`);
          streamMeta.sessionId = chunk.sessionId;
          streamMeta.messageId = chunk.messageId;
          client.emit('message-chunk', {
            done: true,
            sessionId: chunk.sessionId,
            messageId: chunk.messageId,
            tokenUsage: chunk.tokenUsage,
          });
          break;
        } else {
          streamMeta.tokenCount++;
          streamMeta.buffer += chunk.token || '';
          if (chunk.sessionId) {
            streamMeta.sessionId = chunk.sessionId;
          }
          if (chunk.messageId) {
            streamMeta.messageId = chunk.messageId;
          }
          client.emit('message-chunk', {
            token: chunk.token,
            done: false,
          });
        }
      }
    } catch (error) {
      this.logger.error(`❌ Stream error for ${client.id}:`, error.stack || error);

      if (error.name === 'AbortError' || abortController.signal.aborted) {
        client.emit('message-stopped', { reason: 'Stream aborted' });
      } else {
        client.emit('message-error', {
          error: error.message || 'Stream error occurred'
        });
      }
    } finally {
      this.chatService.unregisterRequest(requestId);
      this.activeStreams.delete(client.id);
      this.logger.log(`🧹 Cleanup completed for ${client.id}`);
    }
  }

  /**
   * Stop streaming
   */
  @SubscribeMessage('stop-stream')
  handleStopStream(@ConnectedSocket() client: Socket) {
    this.logger.log(`⏹️ Stop stream requested by ${client.id}`);
    this.stopStreamForSocket(client.id);
    // Partial content will be emitted in the stream loop when abort is detected
  }

  private stopStreamForSocket(socketId: string) {
    const streamMeta = this.activeStreams.get(socketId);
    if (streamMeta) {
      streamMeta.controller.abort();
      // Metadata cleanup will happen in the stream loop when abort is detected
      this.logger.log(`✅ Stream abort signal sent for ${socketId}`);
    }
  }
}
