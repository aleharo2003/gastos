import { BadGatewayException, BadRequestException, Body, Controller, Get, HttpCode, HttpException, Param, Post, Query, Req, Res, UnauthorizedException } from '@nestjs/common';
import type { Request, Response } from 'express';
import { AuthService } from './auth.service.js';
import { boundedJson } from './token-verifier.js';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
type ExpenseInput = { id: string; fecha: string; descripcion: string; moneda: string; importe: string };
type Expense = ExpenseInput & { espacio_id: string; cuenta_id: string };
function valid(value: unknown): value is ExpenseInput {
  const row = value as ExpenseInput;
  return !!row && typeof row.id === 'string' && UUID.test(row.id) && !/^0{8}-0{4}-0{4}-0{4}-0{12}$/.test(row.id) &&
    typeof row.fecha === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(row.fecha) &&
    typeof row.descripcion === 'string' && [...row.descripcion.trim()].length >= 1 && [...row.descripcion.trim()].length <= 160 &&
    !/[\x00-\x1f\x7f]/.test(row.descripcion) && ['ARS','USD','EUR'].includes(row.moneda) &&
    typeof row.importe === 'string' && /^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?$/.test(row.importe) && /[1-9]/.test(row.importe);
}
function expense(value: unknown, space: string, account: string): Expense {
  const row = value as Expense;
  if (!valid(row) || row.espacio_id !== space || row.cuenta_id !== account) throw new Error();
  return { id: row.id, espacio_id: space, cuenta_id: account, fecha: row.fecha, descripcion: row.descripcion, moneda: row.moneda, importe: row.importe };
}

@Controller('api/spaces/:space/accounts/:account/expenses')
export class ExpensesController {
  constructor(private readonly auth: AuthService) {}

  @Get()
  async list(@Param('space') space: string, @Param('account') account: string, @Query('offset') offset: string | undefined, @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    response.setHeader('Cache-Control', 'no-store');
    const token = await this.token(request, response);
    if (offset !== undefined && (typeof offset !== 'string' || !/^\d{1,6}$/.test(offset) || Number(offset) > 100000)) throw new BadRequestException('Pagina invalida');
    return this.forward(token, space, account, undefined, Number(offset ?? 0));
  }

  @Post()
  @HttpCode(200)
  async create(@Param('space') space: string, @Param('account') account: string, @Body() body: unknown, @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    response.setHeader('Cache-Control', 'no-store');
    const token = await this.token(request, response);
    if (!valid(body) || Object.keys(body).some(key => !['id','fecha','descripcion','moneda','importe'].includes(key))) throw new BadRequestException('Gasto invalido');
    return this.forward(token, space, account, { ...body, id: body.id.toLowerCase(), descripcion: body.descripcion.trim() });
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

  private async forward(token: string, rawSpace: string, rawAccount: string, body?: ExpenseInput, offset = 0) {
    if (!UUID.test(rawSpace) || !UUID.test(rawAccount)) throw new BadRequestException('Espacio invalido');
    const space = rawSpace.toLowerCase();
    const account = rawAccount.toLowerCase();
    try {
      const base = new URL(process.env.API_BASE_URL ?? 'http://127.0.0.1:8000');
      const local = ['localhost', '127.0.0.1', '[::1]', 'api'].includes(base.hostname);
      if (base.username || base.password || base.search || base.hash || base.pathname !== '/' ||
          (base.protocol !== 'https:' && !(base.protocol === 'http:' && local))) throw new Error();
      const rawTimeout = process.env.API_TIMEOUT_MS ?? '5000';
      const timeout = Number(rawTimeout);
      if (!/^\d+$/.test(rawTimeout) || !Number.isSafeInteger(timeout) || timeout < 1 || timeout > 2147483647) throw new Error();
      const result = await fetch(new URL(`/spaces/${space}/accounts/${account}/expenses?offset=${offset}`, base), {
        method: body ? 'POST' : 'GET', redirect: 'error', signal: AbortSignal.timeout(timeout),
        headers: { Accept: 'application/json', Authorization: `Bearer ${token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      if ([400, 401, 403, 404, 409, 422, 503].includes(result.status)) throw new HttpException('No se pudo completar la operacion', result.status);
      if (!result.ok) throw new Error();
      const data = await boundedJson(result, 131072);
      if (body) return expense(data, space, account);
      const page = data as { items: unknown[]; next_offset: number | null };
      if (!page || !Array.isArray(page.items) || page.items.length > 100 ||
          !(page.next_offset === null || page.next_offset === offset + 100)) throw new Error();
      return { items: page.items.map(item => expense(item, space, account)), next_offset: page.next_offset };
    } catch (error) {
      if (error instanceof HttpException) throw error;
      throw new BadGatewayException('No se pudo consultar FastAPI');
    }
  }
}
