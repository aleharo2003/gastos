import { Controller, Get, Post, Req, Res, UnauthorizedException } from '@nestjs/common';
import type { Request, Response } from 'express';
import { AuthService } from './auth.service.js';

@Controller('api')
export class AuthController {
  constructor(private readonly auth: AuthService) {}

  @Post('personal-space')
  async personalSpace(@Req() request: Request, @Res({ passthrough: true }) response: Response) {
    return this.respond(request, response, true);
  }

  @Get('me')
  async me(@Req() request: Request, @Res({ passthrough: true }) response: Response): Promise<{ usuario_id: string }> {
    return this.respond(request, response, false);
  }

  private async respond(request: Request, response: Response, personal: boolean) {
    response.setHeader('Cache-Control', 'no-store');
    try {
      const count = request.rawHeaders.filter((value, i) => i % 2 === 0 && value.toLowerCase() === 'authorization').length;
      const header = request.headers.authorization;
      const parts = typeof header === 'string' ? header.trim().split(/\s+/) : [];
      if (count !== 1 || parts.length !== 2 || parts[0].toLowerCase() !== 'bearer') throw new UnauthorizedException('No autenticado');
      return personal ? await this.auth.getPersonalSpace(parts[1]) : await this.auth.getMe(parts[1]);
    } catch (error) {
      if (error instanceof UnauthorizedException) response.setHeader('WWW-Authenticate', 'Bearer');
      throw error;
    }
  }
}
