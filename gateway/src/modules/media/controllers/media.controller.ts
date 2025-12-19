import { Controller, Post, Get, Param } from '@nestjs/common';
import { MediaService } from '../services/media.service';

@Controller('media')
export class MediaController {
  constructor(private mediaService: MediaService) {}

  @Post('upload-url')
  async getUploadUrl() {
    return this.mediaService.getPresignedUrl();
  }

  @Get(':id')
  async getMedia(@Param('id') id: string) {
    return this.mediaService.getMedia(id);
  }
}


