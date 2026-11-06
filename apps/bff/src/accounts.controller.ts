import { BadGatewayException, BadRequestException, Body, Controller, Get, HttpCode, HttpException, Param, Post, Query, Req, Res, UnauthorizedException } from '@nestjs/common';
import type { Request, Response } from 'express';
import { AuthService } from './auth.service.js';
import { boundedJson } from './token-verifier.js';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
type Account = { id: string; espacio_id: string; nombre: string };
function account(value: unknown, space: string): Account {
  const row = value as Account;
  if (!row || typeof row.id !== 'string' || !UUID.test(row.id) || row.espacio_id !== space ||
      typeof row.nombre !== 'string' || row.nombre.length === 0 || row.nombre.length > 160) throw new Error();
  return { id: row.id, espacio_id: row.espacio_id, nombre: row.nombre };
}

@Controller('api/spaces/:space/accounts')
export class AccountsController {
  constructor(private readonly auth: AuthService) {}

  @Get()
  async list(@Param('space') space: string, @Query('offset') offset: string | undefined, @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    response.setHeader('Cache-Control', 'no-store');
    const token = await this.token(request, response);
    if (offset !== undefined && (typeof offset !== 'string' || !/^\d{1,6}$/.test(offset) || Number(offset) > 100000)) throw new BadRequestException('Pagina invalida');
    return this.forward(token, space, undefined, Number(offset ?? 0));
  }

  @Post()
  @HttpCode(200)
  async create(@Param('space') space: string, @Body() body: unknown, @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    response.setHeader('Cache-Control', 'no-store');
    const token = await this.token(request, response);
    const data = body as { id?: unknown; nombre?: unknown };
    if (!data || Object.keys(data).some(key => !['id', 'nombre'].includes(key)) ||
        typeof data.id !== 'string' || !UUID.test(data.id) ||
        typeof data.nombre !== 'string' || [...data.nombre.trim()].length < 1 ||
        [...data.nombre.trim()].length > 80 || /[\x00-\x1f\x7f]/.test(data.nombre)) throw new BadRequestException('Cuenta invalida');
    return this.forward(token, space, { id: data.id.toLowerCase(), nombre: data.nombre.trim() });
  }

  private async token(request: Request, response: Response) {
    const count = request.rawHeaders.filter((v, i) => i % 2 === 0 && v.toLowerCase() === 'authorization').length;
    const parts = request.headers.authorization?.trim().split(/\s+/) ?? [];
    try {
      if (count !== 1 || parts.length !== 2 || parts[0].toLowerCase() !== 'bearer') throw new UnauthorizedException('No autenticado');
      await this.auth.verifyIdentity(parts[1]);
      return parts[1];
    } catch (error) {
      if (error instanceof UnauthorizedException) response.setHeader('WWW-Authenticate', 'Bearer');
      throw error;
    }
  }

  private async forward(token: string, rawSpace: string, body?: { id: string; nombre: string }, offset = 0) {
    if (!UUID.test(rawSpace)) throw new BadRequestException('Espacio invalido');
    const space = rawSpace.toLowerCase();
    try {
      const base = new URL(process.env.API_BASE_URL ?? 'http://127.0.0.1:8000');
      const local = ['localhost', '127.0.0.1', '[::1]', 'api'].includes(base.hostname);
      if (base.username || base.password || base.search || base.hash || base.pathname !== '/' ||
          (base.protocol !== 'https:' && !(base.protocol === 'http:' && local))) throw new Error();
      const rawTimeout = process.env.API_TIMEOUT_MS ?? '5000';
      const timeout = Number(rawTimeout);
      if (!/^\d+$/.test(rawTimeout) || !Number.isSafeInteger(timeout) || timeout < 1 || timeout > 2147483647) throw new Error();
      const result = await fetch(new URL(`/spaces/${space}/accounts?offset=${offset}`, base), {
        method: body ? 'POST' : 'GET', redirect: 'error', signal: AbortSignal.timeout(timeout),
        headers: { Accept: 'application/json', Authorization: `Bearer ${token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      if ([400, 401, 403, 409, 422, 503].includes(result.status)) throw new HttpException('No se pudo completar la operacion', result.status);
      if (!result.ok) throw new Error();
      const data = await boundedJson(result, 65536);
      if (body) return account(data, space);
      const page = data as { items: unknown[]; next_offset: number | null };
      if (!page || !Array.isArray(page.items) || page.items.length > 100 ||
          !(page.next_offset === null || page.next_offset === offset + 100)) throw new Error();
      return { items: page.items.map(item => account(item, space)), next_offset: page.next_offset };
    } catch (error) {
      if (error instanceof HttpException) throw error;
      throw new BadGatewayException('No se pudo consultar FastAPI');
    }
  }
}
