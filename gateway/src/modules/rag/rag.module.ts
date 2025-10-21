import { Module } from '@nestjs/common';
import { RagController } from './controllers/rag.controller';
import { RagService } from './services/rag.service';

@Module({
  controllers: [RagController],
  providers: [RagService],
  exports: [RagService],
})
export class RagModule {}

