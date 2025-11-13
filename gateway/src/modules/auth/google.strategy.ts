import { Injectable } from '@nestjs/common';
import { PassportStrategy } from '@nestjs/passport';
import { Strategy, VerifyCallback } from 'passport-google-oauth20';
import { AuthService } from './auth.service';

@Injectable()
export class GoogleStrategy extends PassportStrategy(Strategy, 'google') {
  constructor(private readonly authService: AuthService) {
    console.log("GOOGLE_CALLBACK_URL", process.env.GOOGLE_CALLBACK_URL);
    super({
      clientID: process.env.GOOGLE_CLIENT_ID || '',
      clientSecret: process.env.GOOGLE_CLIENT_SECRET || '',
      callbackURL: process.env.GOOGLE_CALLBACK_URL || '',
      scope: [
        'email',
        'profile',
      ],
      accessType: 'offline',
      prompt: 'consent',
    }as any);
  }

  async validate(
    accessToken: string,
    refreshToken: string,
    profile: any,
    done: VerifyCallback,
  ): Promise<any> {
    console.log("profile", profile);

    const { name, emails, photos, id } = profile;
    const user = {
      email: emails[0].value,
      emailVerified: emails[0].verified,
      firstName: name.givenName,
      lastName: name.familyName,

      profileImageUrl: photos[0].value,
      id,
      accessToken,
      refreshToken,
    };
    
    done(null, user);
  }
}

