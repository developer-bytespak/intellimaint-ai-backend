import { Controller, Post, Get, Param, Body } from '@nestjs/common';
import { ChatService } from '../services/chat.service';

@Controller('chat')
export class ChatController {
  constructor(private chatService: ChatService) {}

  @Post()
  async createSession(@Body() createDto: any) {
    return this.chatService.createSession(createDto);
  }

  @Get(':id')
  async getSession(@Param('id') id: string) {
    return this.chatService.getSession(id);
  }
}

