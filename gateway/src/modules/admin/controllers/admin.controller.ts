import { Controller, Get, Post, Put, Delete, Param, Body, UseGuards, Res, Req } from '@nestjs/common';
import { AdminService } from '../services/admin.service';
import { JwtAuthGuard } from 'src/modules/auth/jwt-auth.guard';

 @UseGuards(JwtAuthGuard)
@Controller('admin')
export class AdminController {
  constructor(private adminService: AdminService) {}

  @Get('users')
  async getAllUsers(@Res()res:Response) {
    return this.adminService.getAllUsers(res);
  }

  @Get('uploads')
  async getAllUploads(@Res()res:Response) {
    // Implement logic to get all uploads
    return this.adminService.getAllUploads(res);
  }

  @Get('subscriptions')
  async getAllSubscriptions(@Res()res:Response) {
    // Implement logic to get all subscriptions
    return this.adminService.getAllSubscriptions(res);
  }

  @Get('sessions')
  async getAllSessions(@Res()res:Response) {
    // Implement logic to get all sessions
    return this.adminService.getUserChatStats(res);
  }

    @Get('/dashboard')
    async getPlatformStats(@Res() res: Response , @Req() req:any) {
      // Accept only year from query params
      const y = req.query.year ? parseInt(req.query.year) : undefined;
      return this.adminService.getDashboardStats(res, y);
    }

  // @Put('users/:id/role')
  // async updateUserRole(@Param('id') id: string, @Body() roleDto: any) {
  //   return this.adminService.updateUserRole(id, roleDto);
  // }
}


