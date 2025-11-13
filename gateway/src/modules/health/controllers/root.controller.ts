import { Controller, Get } from '@nestjs/common';

@Controller()
export class RootController {
  @Get()
  root() {
    return {
      status: 'healthy',
      service: 'IntelliMaint AI Gateway',
      version: '1.0.0',
      timestamp: new Date().toISOString(),
    };
  }
}


