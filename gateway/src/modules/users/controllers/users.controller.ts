import { Controller, Get, Put, Param, Body } from '@nestjs/common';
import { UsersService } from '../services/users.service';

@Controller('users')
export class UsersController {
  constructor(private usersService: UsersService) {}

  @Get(':id')
  async getUser(@Param('id') id: string) {
    return this.usersService.findOne(id);
  }

  @Put(':id')
  async updateUser(@Param('id') id: string, @Body() updateDto: any) {
    return this.usersService.update(id, updateDto);
  }
}

