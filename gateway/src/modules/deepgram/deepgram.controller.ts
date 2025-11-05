import { Controller, Post, Body, Res, UseInterceptors, UploadedFile, Req } from '@nestjs/common';
import type { Response, Request } from 'express';
import { DeepgramService } from './deepgram.service';
import { FileInterceptor } from '@nestjs/platform-express';
import { asyncHandler } from 'src/common/helpers/asyncHandler';
import { nestError, nestResponse } from 'src/common/helpers/responseHelpers';

@Controller('deepgram')
export class DeepgramController {
  constructor(private readonly deepgramService: DeepgramService) {}

  // Endpoint for ASR (Audio-to-Text)
  @Post('transcribe')
  @UseInterceptors(FileInterceptor('audio')) 
  transcribeAudio(@UploadedFile() audio: any, @Req() req: Request, @Res() res: Response) {
    return asyncHandler(async (req, res) => {
      if (!audio) {
        return nestError(400, 'No audio file uploaded')(res);
      }

      const transcript = await this.deepgramService.transcribeAudio(audio);
      return nestResponse(200, 'Audio transcribed successfully', transcript)(res);
    })(req, res);
  }

  // Endpoint for TTS (Text-to-Speech)
  @Post('synthesize')
  async synthesizeSpeech(@Body('text') text: string, @Res() res: Response) {
    try {
      const audioBuffer = await this.deepgramService.synthesizeSpeech(text);
      res.setHeader('Content-Type', 'audio/mp3');
      res.send(audioBuffer);
    } catch (error) {
      return res.status(500).json({ error: error.message });
    }
  }
}
