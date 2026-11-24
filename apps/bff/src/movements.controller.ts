import { BadGatewayException, BadRequestException, Controller, Get, HttpException, Param, Query, Req, Res, UnauthorizedException } from '@nestjs/common';
import type { Request, Response } from 'express';
import { AuthService } from './auth.service.js';
import { boundedJson } from './token-verifier.js';

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const day = /^\d{4}-\d{2}-\d{2}$/;
const amount = /^(?:0|[1-9][0-9]*)\.[0-9]{2}$/;
const kinds = ['gasto', 'ingreso', 'transferencia'];
const currencies = ['ARS', 'USD', 'EUR'];
const keys = ['desde', 'hasta', 'tipo', 'moneda', 'cuenta', 'texto', 'cursor', 'categoria'];
const isName = (value: unknown) => value === null || (typeof value === 'string' && value.length <= 160);

type Item = { id: string; fecha: string; tipo: string; descripcion: string; moneda: string; importe: string; origen: string | null; destino: string | null; categoria?: string | null };
type Totals = { moneda: string; ingresos: string; gastos: string; transferencias: string };
type Page = { items: Item[]; totales: Totals[]; next_cursor: string | null };

@Controller('api/spaces/:space/movements')
export class MovementsController {
  constructor(private readonly auth: AuthService) {}

  @Get()
  async list(@Param('space') space: string, @Query() query: Record<string, unknown>, @Req() req: Request,
      @Res({ passthrough: true }) res: Response) {
    res.setHeader('Cache-Control', 'no-store');
    const parts = req.headers.authorization?.trim().split(/\s+/) ?? [];
    const count = req.rawHeaders.filter((value, i) => i % 2 === 0 && value.toLowerCase() === 'authorization').length;
    try {
      if (count !== 1 || parts.length !== 2 || parts[0].toLowerCase() !== 'bearer') throw new UnauthorizedException();
      await this.auth.verifyIdentity(parts[1]);
    } catch (error) {
      if (error instanceof UnauthorizedException) res.setHeader('WWW-Authenticate', 'Bearer');
      throw error;
    }
    if (!uuid.test(space) || Object.entries(query).some(([key, value]) => !keys.includes(key) ||
        typeof value !== 'string' || [...value].length > 160 || /[\x00-\x1f\x7f]/.test(value))) {
      throw new BadRequestException('Filtros inválidos');
    }
    const { desde, hasta, tipo, moneda, cuenta, cursor } = query as Record<string, string | undefined>;
    if ((desde && !day.test(desde)) || (hasta && !day.test(hasta)) || (desde && hasta && desde > hasta) ||
        (tipo && !kinds.includes(tipo)) || (moneda && !currencies.includes(moneda)) ||
        (cuenta && !uuid.test(cuenta)) || (cursor && cursor.length > 70)) {
      throw new BadRequestException('Filtros inválidos');
    }

    try {
      const base = new URL(process.env.API_BASE_URL ?? 'http://127.0.0.1:8000');
      const local = ['localhost', '127.0.0.1', '[::1]', 'api'].includes(base.hostname);
      if (base.username || base.password || base.search || base.hash || base.pathname !== '/' ||
          (base.protocol !== 'https:' && !(base.protocol === 'http:' && local))) throw new Error();
      const rawTimeout = process.env.API_TIMEOUT_MS ?? '5000';
      const timeout = Number(rawTimeout);
      if (!/^\d+$/.test(rawTimeout) || !Number.isSafeInteger(timeout) || timeout < 1 || timeout > 2147483647) throw new Error();
      const url = new URL(`/spaces/${space.toLowerCase()}/movements`, base);
      for (const [key, value] of Object.entries(query)) if (value) url.searchParams.set(key, String(value));
      const result = await fetch(url, {
        headers: { Accept: 'application/json', Authorization: `Bearer ${parts[1]}` },
        redirect: 'error', signal: AbortSignal.timeout(timeout),
      });
      if ([400, 401, 403, 422, 503].includes(result.status)) throw new HttpException('No se pudo consultar el historial', result.status);
      if (!result.ok) throw new Error();
      const page = await boundedJson(result, 131072) as Page;
      if (!page || !Array.isArray(page.items) || page.items.length > 50 ||
          !Array.isArray(page.totales) || page.totales.length > 3 ||
          (page.next_cursor !== null && (typeof page.next_cursor !== 'string' || page.next_cursor.length > 70))) throw new Error();
      const items = page.items.map(row => {
        if (!row || typeof row.id !== 'string' || !uuid.test(row.id) || typeof row.fecha !== 'string' || !day.test(row.fecha) ||
            !kinds.includes(row.tipo) || !currencies.includes(row.moneda) || typeof row.descripcion !== 'string' ||
            row.descripcion.length > 320 || typeof row.importe !== 'string' || !amount.test(row.importe) ||
            !isName(row.origen) || !isName(row.destino) || (row.categoria !== undefined && !isName(row.categoria))) throw new Error();
        const { id, fecha, tipo, descripcion, moneda, importe, origen, destino, categoria } = row;
        return { id, fecha, tipo, descripcion, moneda, importe, origen, destino, ...(categoria === undefined ? {} : { categoria }) };
      });
      const totales = page.totales.map(row => {
        if (!row || !currencies.includes(row.moneda) ||
            ![row.ingresos, row.gastos, row.transferencias].every(value => typeof value === 'string' && amount.test(value))) throw new Error();
        const { moneda, ingresos, gastos, transferencias } = row;
        return { moneda, ingresos, gastos, transferencias };
      });
      return { items, totales, next_cursor: page.next_cursor };
    } catch (error) {
      if (error instanceof HttpException) throw error;
      throw new BadGatewayException('No se pudo consultar FastAPI');
    }
  }
}
