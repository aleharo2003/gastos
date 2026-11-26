import { BadGatewayException, BadRequestException, Body, Controller, Get, HttpCode, HttpException, Param, Patch, Post, Query, Req, Res, UnauthorizedException } from '@nestjs/common';
import type { Request, Response } from 'express';
import { AuthService } from './auth.service.js';
import { boundedJson } from './token-verifier.js';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const profileKeys = ['tipo', 'moneda', 'saldo_inicial', 'dia_cierre', 'dia_vencimiento',
  'fecha_vencimiento', 'tasa_anual'] as const;
type Profile = {
  tipo: string; moneda: string; saldo_inicial: string;
  dia_cierre?: number | null; dia_vencimiento?: number | null;
  fecha_vencimiento?: string | null; tasa_anual?: string | null;
};
type Account = { id: string; espacio_id: string; nombre: string } & Partial<Profile>;
type CreateAccount = { id: string; nombre: string } & Partial<Profile>;

function profile(value: Partial<Profile>): Partial<Profile> {
  if (profileKeys.every(key => value[key] == null)) return {};
  const { tipo, moneda, saldo_inicial, dia_cierre, dia_vencimiento, fecha_vencimiento, tasa_anual } = value;
  if (typeof tipo !== 'string' || !['efectivo', 'banco', 'tarjeta_credito', 'billetera', 'inversion'].includes(tipo)
    || typeof moneda !== 'string' || !['ARS', 'USD', 'EUR'].includes(moneda)
    || typeof saldo_inicial !== 'string' || !/^-?(?:0|[1-9][0-9]{0,11})\.[0-9]{2}$/.test(saldo_inicial)) throw new Error();
  const details: Profile = { tipo, moneda, saldo_inicial };
  if (tipo === 'tarjeta_credito') {
    const validDay = (day: unknown): day is number => typeof day === 'number' && Number.isInteger(day) && day >= 1 && day <= 31;
    if (!validDay(dia_cierre) || !validDay(dia_vencimiento)) throw new Error();
    details.dia_cierre = dia_cierre;
    details.dia_vencimiento = dia_vencimiento;
  } else if (dia_cierre != null || dia_vencimiento != null) throw new Error();
  if (tipo === 'inversion') {
    if (typeof fecha_vencimiento !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(fecha_vencimiento)
      || typeof tasa_anual !== 'string' || !/^(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{1,4})?$/.test(tasa_anual)
      || saldo_inicial.startsWith('-') || saldo_inicial === '0.00') throw new Error();
    details.fecha_vencimiento = fecha_vencimiento;
    details.tasa_anual = tasa_anual;
  } else if (fecha_vencimiento != null || tasa_anual != null) throw new Error();
  return details;
}
function account(value: unknown, space: string): Account {
  const row = value as Account;
  if (!row || typeof row.id !== 'string' || !UUID.test(row.id) || row.espacio_id !== space ||
      typeof row.nombre !== 'string' || row.nombre.length === 0 || row.nombre.length > 160) throw new Error();
  return { id: row.id, espacio_id: row.espacio_id, nombre: row.nombre, ...profile(row) };
}

@Controller('api/spaces/:space/accounts')
export class AccountsController {
  constructor(private readonly auth: AuthService) {}

  @Get()
  async list(@Param('space') space: string, @Query('offset') offset: string | undefined, @Query('inactivas') inactive: unknown, @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    response.setHeader('Cache-Control', 'no-store');
    const token = await this.token(request, response);
    if (offset !== undefined && (typeof offset !== 'string' || !/^\d{1,6}$/.test(offset) || Number(offset) > 100000)) throw new BadRequestException('Pagina invalida');
    if (inactive !== undefined && inactive !== 'true') throw new BadRequestException('Estado invalido');
    return this.forward(token, space, undefined, Number(offset ?? 0), undefined, undefined, inactive === 'true');
  }

  @Post()
  @HttpCode(200)
  async create(@Param('space') space: string, @Body() body: unknown, @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    response.setHeader('Cache-Control', 'no-store');
    const token = await this.token(request, response);
    const data = body as { id?: unknown; nombre?: unknown } & Partial<Profile>;
    if (!data || Object.keys(data).some(key => !['id', 'nombre', ...profileKeys].includes(key)) ||
        typeof data.id !== 'string' || !UUID.test(data.id) ||
        typeof data.nombre !== 'string' || [...data.nombre.trim()].length < 1 ||
        [...data.nombre.trim()].length > 80 || /[\x00-\x1f\x7f]/.test(data.nombre)) throw new BadRequestException('Cuenta invalida');
    let details: Partial<Profile>;
    try { details = profile(data); }
    catch { throw new BadRequestException('Revisá los datos del tipo de cuenta'); }
    return this.forward(token, space, { id: data.id.toLowerCase(), nombre: data.nombre.trim(), ...details });
  }

  @Patch(':account')
  async rename(@Param('space') space: string, @Param('account') id: string, @Body() body: unknown,
      @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    response.setHeader('Cache-Control', 'no-store');
    const token = await this.token(request, response);
    const data = body as { nombre?: unknown; nombre_anterior?: unknown };
    if (!UUID.test(id) || !data || Object.keys(data).some(key => !['nombre', 'nombre_anterior'].includes(key)) ||
        typeof data.nombre !== 'string' || [...data.nombre.trim()].length < 1 || [...data.nombre.trim()].length > 80 ||
        typeof data.nombre_anterior !== 'string' || [...data.nombre_anterior].length < 1 ||
        [...data.nombre_anterior].length > 80 || /[\x00-\x1f\x7f]/.test(data.nombre + data.nombre_anterior)) {
      throw new BadRequestException('Cuenta invalida');
    }
    return this.forward(token, space, { nombre: data.nombre.trim(), nombre_anterior: data.nombre_anterior }, 0, id.toLowerCase());
  }

  @Get(':account')
  async detail(@Param('space') space: string, @Param('account') id: string,
      @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    response.setHeader('Cache-Control', 'no-store');
    const token = await this.token(request, response);
    if (!UUID.test(id)) throw new BadRequestException('Cuenta invalida');
    return this.forward(token, space, undefined, 0, id.toLowerCase(), 'detail');
  }

  @Patch(':account/status')
  async setState(@Param('space') space: string, @Param('account') id: string, @Body() body: unknown,
      @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    response.setHeader('Cache-Control', 'no-store');
    const token = await this.token(request, response);
    const data = body as { activa?: unknown };
    if (!UUID.test(id) || !data || Object.keys(data).length !== 1 || typeof data.activa !== 'boolean') {
      throw new BadRequestException('Cuenta invalida');
    }
    return this.forward(token, space, { activa: data.activa }, 0, id.toLowerCase(), 'status');
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

  private async forward(token: string, rawSpace: string, body?: CreateAccount | { nombre: string; nombre_anterior: string } | { activa: boolean }, offset = 0, accountId?: string,
      action?: 'detail' | 'status', inactive = false) {
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
      const suffix = accountId ? `/${accountId}${action === 'status' ? '/status' : ''}`
        : `?offset=${offset}${inactive ? '&inactivas=true' : ''}`;
      const result = await fetch(new URL(`/spaces/${space}/accounts${suffix}`, base), {
        method: body ? (accountId ? 'PATCH' : 'POST') : 'GET', redirect: 'error', signal: AbortSignal.timeout(timeout),
        headers: { Accept: 'application/json', Authorization: `Bearer ${token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      if ([400, 401, 403, 404, 409, 422, 503].includes(result.status)) throw new HttpException('No se pudo completar la operacion', result.status);
      if (!result.ok) throw new Error();
      const data = await boundedJson(result, 65536);
      if (body || action === 'detail') {
        const row = account(data, space);
        if (accountId && row.id !== accountId) throw new Error();
        if (action) {
          const { activa } = data as { activa?: unknown };
          if (typeof activa !== 'boolean' || (body && 'activa' in body && body.activa !== activa)) throw new Error();
          return { ...row, activa };
        }
        return row;
      }
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
