declare module 'passport-jwt' {
  import { Strategy as PassportStrategy } from 'passport';
  import { Request } from 'express';

  export interface StrategyOptions {
    jwtFromRequest: (req: Request) => string | null;
    secretOrKey: string | Buffer;
    issuer?: string;
    audience?: string;
    algorithms?: string[];
    ignoreExpiration?: boolean;
    passReqToCallback?: boolean;
  }

  export interface JwtPayload {
    [key: string]: any;
    sub?: string;
    iat?: number;
    exp?: number;
  }

  export interface VerifyCallback {
    (payload: JwtPayload, done: (error: any, user?: any) => void): void;
  }

  export class Strategy extends PassportStrategy {
    constructor(
      options: StrategyOptions,
      verify: VerifyCallback
    );
  }

  export namespace ExtractJwt {
    function fromHeader(header_name: string): (req: Request) => string | null;
    function fromBodyField(field_name: string): (req: Request) => string | null;
    function fromUrlQueryParameter(param_name: string): (req: Request) => string | null;
    function fromAuthHeaderWithScheme(auth_scheme: string): (req: Request) => string | null;
    function fromAuthHeaderAsBearerToken(): (req: Request) => string | null;
    function fromExtractors(extractors: Array<(req: Request) => string | null>): (req: Request) => string | null;
  }
}
