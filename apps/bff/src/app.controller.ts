import { Controller, Get, Header } from '@nestjs/common';
import { AppService } from './app.service.js';

@Controller()
export class AppController {
  constructor(private readonly appService: AppService) {}

  @Get()
  getHello(): string {
    return this.appService.getHello();
  }

  @Get('health')
  getHealth(): { status: string } {
    return { status: 'ok' };
  }

  @Get('version')
  @Header('Cache-Control', 'no-store')
  getVersion(): { commit: string | null } {
    return { commit: process.env.RENDER_GIT_COMMIT ?? null };
  }

  @Get('api/hello')
  getApiMessage(): Promise<{ message: string }> {
    return this.appService.getApiMessage();
  }
}
