import { BadGatewayException, BadRequestException, Body, Controller, Get, HttpException, Param, Post, Req, Res, UnauthorizedException } from '@nestjs/common';
import type { Request, Response } from 'express';
import { AuthService } from './auth.service.js';
import { boundedJson } from './token-verifier.js';

const uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;

@Controller('api/spaces/:space/accounts/:account/expense-import')
export class ExpenseImportController {
  constructor(private readonly auth: AuthService) {}

  @Get()
  list(@Param() params: Record<string, string>, @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    return this.forward(params, request, response, 'GET');
  }

  @Post()
  commit(@Param() params: Record<string, string>, @Body() body: unknown, @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    return this.forward(params, request, response, 'POST', '', body);
  }

  @Post('preview')
  preview(@Param() params: Record<string, string>, @Body() body: unknown, @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    return this.forward(params, request, response, 'POST', '/preview', body);
  }

  @Post(':batch/void')
  cancel(@Param() params: Record<string, string>, @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    if (!uuid.test(params['batch'])) throw new BadRequestException('Lote inválido');
    return this.forward(params, request, response, 'POST', '/' + params['batch'] + '/void');
  }

  private async forward(params: Record<string, string>, request: Request, response: Response,
    method: 'GET' | 'POST', suffix = '', body?: unknown) {
    response.setHeader('Cache-Control', 'no-store');
    const parts = request.headers.authorization?.trim().split(/\s+/) ?? [];
    const count = request.rawHeaders.filter((header, index) => index % 2 === 0 && header.toLowerCase() === 'authorization').length;
    if (count !== 1 || parts.length !== 2 || parts[0].toLowerCase() !== 'bearer') {
      response.setHeader('WWW-Authenticate', 'Bearer');
      throw new UnauthorizedException();
    }
    await this.auth.verifyIdentity(parts[1]);
    const { space, account } = params;
    if (!uuid.test(space) || !uuid.test(account)) throw new BadRequestException('Cuenta o espacio inválido');
    const kind = request.query['tipo'];
    if (kind !== undefined && kind !== 'gasto' && kind !== 'ingreso' && kind !== 'transferencia') {
      throw new BadRequestException('Tipo inválido');
    }
    const destination = request.query['destino'];
    if (kind === 'transferencia' && (typeof destination !== 'string' || !uuid.test(destination))) {
      throw new BadRequestException('Destino inválido');
    }
    if (kind !== 'transferencia' && destination !== undefined) throw new BadRequestException('Destino inesperado');
    const json = body === undefined ? undefined : JSON.stringify(body);
    if (json && Buffer.byteLength(json) > 90 * 1024) throw new HttpException('Dividí el archivo en partes más chicas', 413);
    try {
      const base = new URL(process.env.API_BASE_URL ?? 'http://127.0.0.1:8000');
      const local = ['localhost', '127.0.0.1', '[::1]', 'api'].includes(base.hostname);
      if (base.username || base.password || base.search || base.hash || base.pathname !== '/' ||
          (base.protocol !== 'https:' && !(base.protocol === 'http:' && local))) throw new Error();
      const url = new URL('/spaces/' + space + '/accounts/' + account + '/expense-import' + suffix, base);
      if (kind) url.searchParams.set('tipo', kind);
      if (typeof destination === 'string') url.searchParams.set('destino', destination);
      const result = await fetch(url, {
        method, body: json, redirect: 'error', signal: AbortSignal.timeout(20_000),
        headers: { Accept: 'application/json', Authorization: 'Bearer ' + parts[1],
          ...(json ? { 'Content-Type': 'application/json' } : {}) },
      });
      if (!result.ok) {
        await result.body?.cancel();
        if ([400, 401, 403, 404, 409, 413, 422, 503].includes(result.status)) {
          throw new HttpException('No se pudo completar la importación', result.status);
        }
        throw new Error();
      }
      return await boundedJson(result, 32_768);
    } catch (error) {
      if (error instanceof HttpException) throw error;
      throw new BadGatewayException('No se pudo consultar la importación');
    }
  }
}
