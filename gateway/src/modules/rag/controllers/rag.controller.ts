import { Controller, Post, Get, Delete, Param, Body } from '@nestjs/common';
import { RagService } from '../services/rag.service';

@Controller('documents')
export class RagController {
  constructor(private ragService: RagService) {}

  @Post('ingest')
  async ingestDocument(@Body() ingestDto: any) {
    return this.ragService.ingestDocument(ingestDto);
  }

  @Get(':id')
  async getDocument(@Param('id') id: string) {
    return this.ragService.getDocument(id);
  }

  @Delete(':id')
  async deleteDocument(@Param('id') id: string) {
    return this.ragService.deleteDocument(id);
  }
}

