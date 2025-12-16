import { Module } from '@nestjs/common';
import { ChatController } from './controllers/chat.controller';
import { ChatService } from './services/chat.service';
import { GeminiChatService } from './services/gemini-chat.service';
import { ImageUtilService } from './services/image-util.service';
import { VercelBlobService } from './services/vercel-blob.service';
import { ChatGateway } from './gateway/chat.gateway';
import { SocketChatGateway } from './gateway/socket-chat.gateway';
import { PrismaService } from 'prisma/prisma.service';

@Module({
  controllers: [ChatController],
  providers: [
    ChatService,
    GeminiChatService,
    ImageUtilService,
    VercelBlobService,
    ChatGateway,
    SocketChatGateway,
    PrismaService,
  ],
  exports: [ChatService],
})
export class ChatModule {}
