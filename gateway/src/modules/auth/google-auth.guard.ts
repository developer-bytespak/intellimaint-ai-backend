import { Injectable, ExecutionContext } from '@nestjs/common';
import { AuthGuard } from '@nestjs/passport';
import { Response } from 'express';

@Injectable()
export class GoogleAuthGuard extends AuthGuard('google') {
  async canActivate(context: ExecutionContext): Promise<boolean> {
    const request = context.switchToHttp().getRequest();
    const response: Response = context.switchToHttp().getResponse();

    // Check if user already has a valid cookie
    const token = request.cookies?.jwt;

    if (token) {
      // User has a token, redirect to chat
      response.redirect('http://localhost:3001/chat');
      return false; // Prevent further execution
    }

    // No token, proceed with Google OAuth
    return super.canActivate(context) as Promise<boolean>;
  }
}

