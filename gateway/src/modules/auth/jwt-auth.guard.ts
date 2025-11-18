import { CanActivate, ExecutionContext, Injectable } from '@nestjs/common';
import axios from 'axios';
import { Response } from 'express';

// JwtAuthGuard.ts (Suggested changes)

// ... imports

@Injectable()
export class JwtAuthGuard implements CanActivate {
  // Google API se interact karne ke liye service banaana padega
  // Isko alag service mein daalna better hai, lekin filhaal yahan dekhein.

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const request = context.switchToHttp().getRequest();
    const response: Response = context.switchToHttp().getResponse();

    const googleAccessToken = request.cookies?.jwt; // Assuming 'jwt' is Google's Access Token

    if (!googleAccessToken) {
      response.redirect('/auth/google');
      return false;
    }

    try {
      // Google ke Token Info Endpoint ko call karein
      // Taa ke pata chale ke token valid hai ya nahi
      // const info =await axios.get(
      //   `https://www.googleapis.com/oauth2/v3/tokeninfo?access_token=${googleAccessToken}`
      // );
      // const tokenInfo = info.data;

      // if (tokenInfo.error_description) {
      //   // Token expired hai ya invalid
      //   throw new Error(tokenInfo.error_description);
      // }

      // Agar token valid hai, toh user ki zaroori info req.user mein save karein
      // User ki email ya ID mil jaegi yahan se
      // request.user = { email: tokenInfo.email, accessToken: googleAccessToken };
      return true;
    } catch (e) {
      console.error('Google Token verification failed:', e.message);
      // ... clearCookie and redirect code remains same ...
      response.redirect('/auth/google');
      return false;
    }
  }
}