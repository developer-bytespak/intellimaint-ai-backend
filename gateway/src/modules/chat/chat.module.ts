import { Module } from '@nestjs/common';
import { ChatController } from './controllers/chat.controller';
import { ChatService } from './services/chat.service';
import { OpenAIChatService } from './services/openai-chat.service';
import { ImageUtilService } from './services/image-util.service';
import { VercelBlobService } from './services/vercel-blob.service';
import { ChatGateway } from './gateway/chat.gateway';
import { SocketChatGateway } from './gateway/socket-chat.gateway';
import { PrismaService } from 'prisma/prisma.service';
import { OpenAIVisionService } from './services/openai-vision.service';
import { OpenAIEmbeddingService } from './services/openai-embedding.service';
import { RagRetrievalService } from './services/rag-retrieval.service';
import { ContextManagerService } from './services/context-manager.service';
import { OpenAILLMService } from './services/openai-llm.service';
import { ChatTitleService } from './services/chat-title.service';

@Module({
  controllers: [ChatController],
  providers: [
    ChatService,
    OpenAIChatService,
    ImageUtilService,
    VercelBlobService,
    ChatGateway,
    SocketChatGateway,
    PrismaService,
    OpenAIVisionService,
    OpenAIEmbeddingService,
    RagRetrievalService,
    ContextManagerService,
    OpenAILLMService,
    ChatTitleService,
  ],
  exports: [ChatService],
})
export class ChatModule {}
