import { Module } from '@nestjs/common';
import { DeepgramService } from './deepgram.service';
import { DeepgramController } from './deepgram.controller';

@Module({
  providers: [DeepgramService],
  controllers: [DeepgramController],
})
export class DeepgramModule {}
