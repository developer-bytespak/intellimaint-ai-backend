import { Controller, Get, Post, Put, Delete, Param, Body, UseGuards } from '@nestjs/common';
import { AdminService } from '../services/admin.service';

@Controller('admin')
export class AdminController {
  constructor(private adminService: AdminService) {}

  @Get('users')
  async getAllUsers() {
    return this.adminService.getAllUsers();
  }

  @Put('users/:id/role')
  async updateUserRole(@Param('id') id: string, @Body() roleDto: any) {
    return this.adminService.updateUserRole(id, roleDto);
  }
}

