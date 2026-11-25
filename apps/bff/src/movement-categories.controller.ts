import { BadGatewayException, BadRequestException, Controller, Get, HttpException, Param, Req, Res, UnauthorizedException } from '@nestjs/common';
import type { Request, Response } from 'express';
import { AuthService } from './auth.service.js';
import { boundedJson } from './token-verifier.js';

const id = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
type Category = { id: string; tipo: 'gasto' | 'ingreso'; nombre: string; activa: boolean };

function asCategory(value: unknown): Category {
  const row = value as Category | null;
  if (!row || typeof row.id !== 'string' || !/^[a-z0-9_-]{1,36}$/.test(row.id) ||
      !['gasto', 'ingreso'].includes(row.tipo) || typeof row.nombre !== 'string' ||
      !row.nombre.trim() || [...row.nombre].length > 80 || typeof row.activa !== 'boolean') throw new Error();
  return { id: row.id, tipo: row.tipo, nombre: row.nombre, activa: row.activa };
}

@Controller('api/spaces/:space/categories')
export class MovementCategoriesController {
  constructor(private readonly auth: AuthService) {}

  @Get()
  async list(@Param('space') space: string, @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    const value = await this.forward(space, request, response) as { items?: unknown[] } | null;
    try {
      if (!Array.isArray(value?.items) || value.items.length > 100) throw new Error();
      return { items: value.items.map(asCategory) };
    } catch {
      throw new BadGatewayException('No se pudo consultar el catálogo');
    }
  }

  private async forward(space: string, request: Request, response: Response): Promise<unknown> {
    response.setHeader('Cache-Control', 'no-store');
    const parts = request.headers.authorization?.trim().split(/\s+/) ?? [];
    const count = request.rawHeaders.filter((header, index) => index % 2 === 0 && header.toLowerCase() === 'authorization').length;
    try {
      if (count !== 1 || parts.length !== 2 || parts[0].toLowerCase() !== 'bearer') throw new UnauthorizedException();
      await this.auth.verifyIdentity(parts[1]);
    } catch (error) {
      if (error instanceof UnauthorizedException) response.setHeader('WWW-Authenticate', 'Bearer');
      throw error;
    }
    if (!id.test(space)) throw new BadRequestException('Espacio inválido');
    try {
      const base = new URL(process.env.API_BASE_URL ?? 'http://127.0.0.1:8000');
      const local = ['localhost', '127.0.0.1', '[::1]', 'api'].includes(base.hostname);
      if (base.username || base.password || base.search || base.hash || base.pathname !== '/' ||
          (base.protocol !== 'https:' && !(base.protocol === 'http:' && local))) throw new Error();
      const rawTimeout = process.env.API_TIMEOUT_MS ?? '5000';
      const timeout = Number(rawTimeout);
      if (!/^\d+$/.test(rawTimeout) || !Number.isSafeInteger(timeout) || timeout < 1 || timeout > 2147483647) throw new Error();
      const result = await fetch(new URL('/spaces/' + space.toLowerCase() + '/categories', base), {
        headers: { Accept: 'application/json', Authorization: 'Bearer ' + parts[1] },
        redirect: 'error', signal: AbortSignal.timeout(timeout),
      });
      if ([400, 401, 403, 409, 422, 503].includes(result.status)) {
        throw new HttpException('No se pudo consultar el catálogo', result.status);
      }
      if (!result.ok) throw new Error();
      return await boundedJson(result, 32768);
    } catch (error) {
      if (error instanceof HttpException) throw error;
      throw new BadGatewayException('No se pudo consultar el catálogo');
    }
  }
}
