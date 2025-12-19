import { Controller, Post, Get, Param, UseGuards } from '@nestjs/common';
import { MediaService } from '../services/media.service';
import { JwtAuthGuard } from 'src/modules/auth/jwt-auth.guard';

@Controller('media')
@UseGuards(JwtAuthGuard)
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

