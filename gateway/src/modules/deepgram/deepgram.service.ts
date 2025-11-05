import { Injectable } from '@nestjs/common';
import { createClient } from '@deepgram/sdk';
import * as dotenv from 'dotenv';
dotenv.config();

@Injectable()
export class DeepgramService {
  private readonly client;

  constructor() {
    const DEEPGRAM_API_KEY = process.env.DEEPGRAM_API_KEY;
    this.client = createClient(DEEPGRAM_API_KEY);
  }

  // ASR (Automatic Speech Recognition) - Transcribe Audio to Text
  async transcribeAudio(audio: { buffer: Buffer; mimetype: string }): Promise<string> {
    try {
      const { result, error } = await this.client.listen.prerecorded.transcribeFile(
        audio.buffer,
        {
          model: 'nova-3',
          language: 'en-US',
          punctuate: true,
          mimetype: audio.mimetype
        }
      );
      if (error) throw new Error(error.message);
      return result?.results?.channels?.[0]?.alternatives?.[0]?.transcript || '';
    } catch (error) {
      throw new Error(`Transcription failed: ${error.message}`);
    }
  }

  // TTS (Text-to-Speech) - Convert Text to Speech Audio
  async synthesizeSpeech(text: string): Promise<Buffer> {
    try {
        
      const { result, error } = await this.client.speak.request(
        { text },
        {
          model: "aura-2-thalia-en",
          encoding: "linear16",
          container: "wav",
        }
      );

      if (error) throw new Error(error.message);

      const audioBuffer = await result.arrayBuffer();
      return Buffer.from(audioBuffer);
    } catch (error) {
      console.log(error,'error');
      throw new Error(`TTS generation failed: ${error.message}`);
    }
  }
}
