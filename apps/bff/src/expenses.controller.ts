import { BadGatewayException, BadRequestException, Body, Controller, Get, HttpCode, HttpException, Param, Patch, Post, Query, Req, Res, UnauthorizedException } from '@nestjs/common';
import type { Request, Response } from 'express';
import { AuthService } from './auth.service.js';
import { boundedJson } from './token-verifier.js';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const CATEGORIES = ["alimentos", "transporte", "vivienda", "servicios", "salud", "educacion", "ocio", "impuestos", "auto", "bancario", "ropa", "otros"];
const isExpenseCategory = (value: unknown): value is string =>
  typeof value === 'string' && (CATEGORIES.includes(value) || UUID.test(value));
type ExpenseInput = { id: string; fecha: string; descripcion: string; moneda: string; importe: string;
  categoria?: string | null; nota?: string | null; fecha_devengamiento?: string | null; fecha_vencimiento?: string | null };
const expenseFields = ['id', 'fecha', 'descripcion', 'moneda', 'importe', 'categoria', 'nota',
  'fecha_devengamiento', 'fecha_vencimiento'];
const isoDate = (value: unknown): value is string => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value);
type Expense = ExpenseInput & { espacio_id: string; cuenta_id: string; coincidencia_aproximada?: boolean; cuenta_nombre?: string; pago_cuota?: boolean };
type ExpenseEdit = { original: ExpenseInput; nuevo: ExpenseInput };
type PendingExpense = Omit<ExpenseInput, 'fecha'>;
type PendingPayment = Pick<ExpenseInput, 'fecha'>;
function valid(value: unknown): value is ExpenseInput {
  const row = value as ExpenseInput;
  return !!row && (row.nota == null || (typeof row.nota === 'string' && [...row.nota.trim()].length <= 500 && !/[\x00-\x1f\x7f]/.test(row.nota.trim()))) && (row.categoria == null || isExpenseCategory(row.categoria)) && typeof row.id === 'string' && UUID.test(row.id) && !/^0{8}-0{4}-0{4}-0{4}-0{12}$/.test(row.id) &&
    isoDate(row.fecha) && (row.fecha_devengamiento == null || isoDate(row.fecha_devengamiento)) &&
    (row.fecha_vencimiento == null || isoDate(row.fecha_vencimiento)) &&
    typeof row.descripcion === 'string' && [...row.descripcion.trim()].length >= 1 && [...row.descripcion.trim()].length <= 160 &&
    !/[\x00-\x1f\x7f]/.test(row.descripcion) && ['ARS','USD','EUR'].includes(row.moneda) &&
    typeof row.importe === 'string' && /^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?$/.test(row.importe) && /[1-9]/.test(row.importe);
}
function expense(value: unknown, space: string, account: string | undefined): Expense {
  const row = value as Expense;
  if (row?.coincidencia_aproximada !== undefined && typeof row.coincidencia_aproximada !== 'boolean') throw new Error();
  if (row?.pago_cuota !== undefined && typeof row.pago_cuota !== 'boolean') throw new Error();
  if (row?.cuenta_nombre !== undefined && (typeof row.cuenta_nombre !== 'string' || row.cuenta_nombre.length < 1 || row.cuenta_nombre.length > 160)) throw new Error();
  if (!valid(row) || row.espacio_id !== space || (account !== undefined ? row.cuenta_id !== account : typeof row.cuenta_id !== 'string' || !UUID.test(row.cuenta_id))) throw new Error();
  return { id: row.id, espacio_id: space, cuenta_id: row.cuenta_id, fecha: row.fecha, descripcion: row.descripcion, moneda: row.moneda, importe: row.importe, ...(row.cuenta_nombre !== undefined ? {cuenta_nombre:row.cuenta_nombre} : {}), ...(row.nota != null ? { nota: row.nota } : {}), ...(row.categoria !== undefined ? {categoria:row.categoria} : {}), ...(row.coincidencia_aproximada !== undefined ? {coincidencia_aproximada:row.coincidencia_aproximada} : {}), ...(row.pago_cuota ? { pago_cuota: true } : {}),
    ...(row.fecha_devengamiento != null ? { fecha_devengamiento: row.fecha_devengamiento } : {}),
    ...(row.fecha_vencimiento != null ? { fecha_vencimiento: row.fecha_vencimiento } : {}) };
}

@Controller('api/spaces/:space')
export class ExpensesController {
  constructor(private readonly auth: AuthService) {}

  @Get('expenses')
  async all(@Param('space') space: string, @Query() query: Record<string, unknown>, @Req() request: Request, @Res({passthrough:true}) response: Response) {
    return this.list(space, undefined, query, request, response);
  }

  @Get('expense-summary')
  async summary(@Param('space') space: string, @Query() query: Record<string,unknown>, @Req() request: Request, @Res({passthrough:true}) response: Response) {
    response.setHeader('Cache-Control','no-store');
    const token = await this.token(request,response);
    if (Object.keys(query).some(k => k !== 'account') || (query.account !== undefined && (typeof query.account !== 'string' || !UUID.test(query.account)))) throw new BadRequestException('Cuenta invalida');
    return this.forward(token,space,query.account as string | undefined,undefined,0,undefined,new URLSearchParams(),false,undefined,'expense-summary');
  }

  @Get('expense-trend')
  async trend(@Param('space') space: string, @Query() query: Record<string, unknown>,
    @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    response.setHeader('Cache-Control', 'no-store');
    const token = await this.token(request, response);
    if (Object.keys(query).some(key => key !== 'account') ||
        (query.account !== undefined && (typeof query.account !== 'string' || !UUID.test(query.account)))) {
      throw new BadRequestException('Cuenta invalida');
    }
    return this.forward(token, space, query.account as string | undefined, undefined, 0, undefined,
      new URLSearchParams(), false, undefined, 'expense-trend');
  }

  @Get('expense-category-summary')
  async categorySummary(@Param('space') space: string, @Query() query: Record<string, unknown>,
    @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    response.setHeader('Cache-Control', 'no-store');
    const token = await this.token(request, response);
    if (Object.keys(query).some(key => !['account', 'mes'].includes(key)) ||
        (query.account !== undefined && (typeof query.account !== 'string' || !UUID.test(query.account))) ||
        (query.mes !== undefined && (typeof query.mes !== 'string' || !/^(19[0-9]{2}|20[0-9]{2})-(0[1-9]|1[0-2])$/.test(query.mes)))) {
      throw new BadRequestException('Cuenta o mes inválido');
    }
    const filters = new URLSearchParams();
    if (typeof query.mes === 'string') filters.set('mes', query.mes);
    return this.forward(token, space, query.account as string | undefined, undefined, 0, undefined,
      filters, false, undefined, 'expense-category-summary');
  }

  @Get('accounts/:account/expenses')
  async list(@Param('space') space: string, @Param('account') account: string | undefined, @Query() query: Record<string, unknown>, @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    response.setHeader('Cache-Control', 'no-store');
    const token = await this.token(request, response);
    const offset = query.offset;
    if (offset !== undefined && (typeof offset !== 'string' || !/^\d{1,6}$/.test(offset) || Number(offset) > 100000)) throw new BadRequestException('Pagina invalida');
    const filters = new URLSearchParams();
    for (const key of Object.keys(query)) {
      if (!['offset','desde','hasta','categoria','moneda','texto','aproximada'].includes(key)) throw new BadRequestException('Filtro invalido');
      if (key === 'offset') continue;
      const value = query[key];
      if (typeof value !== 'string' || value.length > 160 || /[\x00-\x1f\x7f]/.test(value)) throw new BadRequestException('Filtro invalido');
      if (['desde','hasta'].includes(key) && !/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new BadRequestException('Fecha invalida');
      if (key === 'categoria' && value !== 'sin_categoria' && !isExpenseCategory(value)) throw new BadRequestException('Categoria invalida');
      if (key === 'moneda' && !['ARS','USD','EUR'].includes(value)) throw new BadRequestException('Moneda invalida');
      if (key === 'aproximada' && !['true','false'].includes(value)) throw new BadRequestException('Modo de busqueda invalido');
      filters.set(key,value);
    }
    return this.forward(token, space, account, undefined, Number(offset ?? 0), undefined, filters);
  }

  @Get('accounts/:account/expenses/category-suggestion')
  async suggestion(@Param('space') space: string, @Param('account') account: string, @Query() query: Record<string,unknown>, @Req() request: Request, @Res({passthrough:true}) response: Response) {
    response.setHeader('Cache-Control','no-store');
    const token = await this.token(request,response);
    const description = query.descripcion;
    if (Object.keys(query).some(k=>k!=='descripcion') || typeof description !== 'string' ||
        [...description.trim()].length < 4 || [...description].length > 160 || /[\x00-\x1f\x7f]/.test(description)) throw new BadRequestException('Descripcion invalida');
    return this.forward(token,space,account,undefined,0,undefined,new URLSearchParams({descripcion:description.trim()}),true);
  }

  @Get('accounts/:account/expenses/:id/similar')
  async similar(@Param('space') space:string,@Param('account') account:string,@Param('id') id:string,@Req() request:Request,@Res({passthrough:true}) response:Response) {
    response.setHeader('Cache-Control','no-store');
    const token=await this.token(request,response);
    if(!UUID.test(id))throw new BadRequestException('Gasto invalido');
    return this.forward(token,space,account,undefined,0,undefined,new URLSearchParams(),false,id.toLowerCase());
  }

  @Post('accounts/:account/expenses')
  @HttpCode(200)
  async create(@Param('space') space: string, @Param('account') account: string, @Body() body: unknown, @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    response.setHeader('Cache-Control', 'no-store');
    const token = await this.token(request, response);
    if (!valid(body) || Object.keys(body).some(key => !expenseFields.includes(key))) throw new BadRequestException('Gasto invalido');
    return this.forward(token, space, account, { ...body, id: body.id.toLowerCase(), descripcion: body.descripcion.trim() });
  }

  @Post('accounts/:account/expenses/pending')
  @HttpCode(200)
  async createPending(@Param('space') space: string, @Param('account') account: string, @Body() body: PendingExpense,
    @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    response.setHeader('Cache-Control', 'no-store');
    const token = await this.token(request, response);
    if (!body || !valid({ ...body, fecha: body.fecha_vencimiento }) ||
        Object.keys(body).some(key => key === 'fecha' || !expenseFields.includes(key))) {
      throw new BadRequestException('Gasto pendiente invalido');
    }
    return this.forward(token, space, account, { ...body, id: body.id.toLowerCase(), descripcion: body.descripcion.trim() },
      0, undefined, new URLSearchParams(), false, undefined, false, undefined, 'pending');
  }

  @Post('accounts/:account/expenses/:id/pay-pending')
  @HttpCode(200)
  async payPending(@Param('space') space: string, @Param('account') account: string, @Param('id') id: string,
    @Body() body: PendingPayment, @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    response.setHeader('Cache-Control', 'no-store');
    const token = await this.token(request, response);
    if (!UUID.test(id) || !body || !isoDate(body.fecha) || Object.keys(body).length !== 1) {
      throw new BadRequestException('Pago invalido');
    }
    return this.forward(token, space, account, body, 0, undefined, new URLSearchParams(),
      false, undefined, false, undefined, id.toLowerCase());
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

  @Patch('accounts/:account/expenses/:id')
  async edit(@Param('space') space: string, @Param('account') account: string, @Param('id') id: string, @Body() value: unknown, @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    response.setHeader('Cache-Control', 'no-store');
    const token = await this.token(request, response);
    const body = value as ExpenseEdit;
    if (!UUID.test(id) || !body || !valid(body.original) || !valid(body.nuevo) ||
        body.original.id.toLowerCase() !== id.toLowerCase() || body.nuevo.id.toLowerCase() !== id.toLowerCase() ||
        Object.keys(body).some(k => !['original','nuevo'].includes(k)) ||
        [body.original,body.nuevo].some(r => Object.keys(r).some(k => !expenseFields.includes(k)))) throw new BadRequestException('Edicion invalida');
    return this.forward(token, space, account, body, 0, id.toLowerCase());
  }

  @Post('accounts/:account/expenses/:id/void')
  @HttpCode(200)
  async voidExpense(@Param('space') space: string, @Param('account') account: string, @Param('id') id: string, @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    response.setHeader('Cache-Control', 'no-store');
    const token = await this.token(request, response);
    if (!UUID.test(id)) throw new BadRequestException('Gasto invalido');
    const target = { id: id.toLowerCase() };
    return this.forward(token, space, account, undefined, 0, undefined, new URLSearchParams(), false, undefined, false, target);
  }

  private async forward(token: string, rawSpace: string, rawAccount: string | undefined, body?: ExpenseInput | ExpenseEdit | PendingExpense | PendingPayment, offset = 0, editId?: string, filters = new URLSearchParams(), suggestion = false, similarId?:string, summary: 'expense-summary' | 'expense-category-summary' | 'expense-trend' | false = false, voidTarget?: { id: string }, pending?: string) {
    if (!UUID.test(rawSpace) || (rawAccount !== undefined && !UUID.test(rawAccount)) || (rawAccount === undefined && !!(body || editId || suggestion || similarId || voidTarget))) throw new BadRequestException('Espacio invalido');
    const space = rawSpace.toLowerCase();
    const account = rawAccount?.toLowerCase();
    try {
      const base = new URL(process.env.API_BASE_URL ?? 'http://127.0.0.1:8000');
      const local = ['localhost', '127.0.0.1', '[::1]', 'api'].includes(base.hostname);
      if (base.username || base.password || base.search || base.hash || base.pathname !== '/' ||
          (base.protocol !== 'https:' && !(base.protocol === 'http:' && local))) throw new Error();
      const rawTimeout = process.env.API_TIMEOUT_MS ?? '5000';
      const timeout = Number(rawTimeout);
      if (!/^\d+$/.test(rawTimeout) || !Number.isSafeInteger(timeout) || timeout < 1 || timeout > 2147483647) throw new Error();
      const summaryParams = new URLSearchParams(filters);
      if (account) summaryParams.set('account', account);
      const pendingPath = pending === 'pending' ? '/pending' : pending ? `/${pending}/pay-pending` : '';
      const result = await fetch(new URL(summary ? `/spaces/${space}/${summary}${summaryParams.size ? '?' + summaryParams : ''}` : `/spaces/${space}${account ? '/accounts/'+account : ''}/expenses${pendingPath || (voidTarget ? '/' + voidTarget.id + '/void' : similarId ? '/' + similarId + '/similar' : suggestion ? '/category-suggestion?' + filters.toString() : editId ? '/' + editId : '?offset=' + offset + (filters.size ? '&' + filters.toString() : ''))}`, base), {
        method: editId ? 'PATCH' : body || voidTarget ? 'POST' : 'GET', redirect: 'error', signal: AbortSignal.timeout(timeout),
        headers: { Accept: 'application/json', Authorization: `Bearer ${token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      if ([400, 401, 403, 404, 409, 422, 503].includes(result.status)) throw new HttpException('No se pudo completar la operacion', result.status);
      if (!result.ok) throw new Error();
      const data = await boundedJson(result, 131072);
      if (pending === 'pending') {
        const result = data as { id: string; pendiente: boolean } | null;
        if (result?.id !== (body as PendingExpense).id || typeof result.pendiente !== 'boolean') throw new Error();
        return { id: result.id, pendiente: result.pendiente };
      }
      if (pending) {
        const result = expense(data, space, account);
        if (result.id !== pending || result.fecha !== (body as PendingPayment).fecha) throw new Error();
        return result;
      }
      if (summary === 'expense-trend') {
        const report = data as { meses: string[]; items: { mes: string; moneda: string; categoria: string | null; total: string }[] };
        if (!report || !Array.isArray(report.meses) || report.meses.length !== 12 ||
            report.meses.some((month, i) => typeof month !== 'string' || !/^\d{4}-(0[1-9]|1[0-2])$/.test(month) ||
              (i > 0 && month <= report.meses[i - 1])) ||
            !Array.isArray(report.items) || report.items.length > 36 * (CATEGORIES.length + 1)) throw new Error();
        const seen = new Set<string>();
        const items = report.items.map(item => {
          if (!item || !report.meses.includes(item.mes) || !['ARS', 'USD', 'EUR'].includes(item.moneda) ||
              (item.categoria !== null && !isExpenseCategory(item.categoria)) ||
              typeof item.total !== 'string' || !/^(?:0|[1-9][0-9]{0,30})\.[0-9]{2}$/.test(item.total)) throw new Error();
          const { mes, moneda, categoria, total } = item;
          const key = mes + ':' + moneda + ':' + (categoria ?? '');
          if (seen.has(key)) throw new Error();
          seen.add(key);
          return { mes, moneda, categoria, total };
        });
        return { meses: report.meses, items };
      }
      if (summary === 'expense-category-summary') {
        const value = data as { desde: string; hasta: string; items: { moneda: string; categoria: string | null; total: string }[] };
        if (!value || typeof value.desde !== 'string' || !/^\d{4}-(0[1-9]|1[0-2])-01$/.test(value.desde) ||
            typeof value.hasta !== 'string' || !/^\d{4}-\d{2}-(28|29|30|31)$/.test(value.hasta) ||
            value.hasta.slice(0, 7) !== value.desde.slice(0, 7) || !Array.isArray(value.items) ||
            value.items.length > 3 * (CATEGORIES.length + 1) || value.items.some(row =>
              !row || !['ARS', 'USD', 'EUR'].includes(row.moneda) ||
              (row.categoria !== null && !isExpenseCategory(row.categoria)) ||
              typeof row.total !== 'string' || !/^(?:0|[1-9][0-9]{0,30})\.[0-9]{2}$/.test(row.total)
            )) throw new Error();
        const requestedMonth = filters.get('mes');
        if (requestedMonth && value.desde !== requestedMonth + '-01') throw new Error();
        if (new Set(value.items.map(row => `${row.moneda}:${row.categoria ?? ''}`)).size !== value.items.length) throw new Error();
        return { desde: value.desde, hasta: value.hasta,
          items: value.items.map(({ moneda, categoria, total }) => ({ moneda, categoria, total })) };
      }
      if (summary === 'expense-summary') {
        const value=data as {fecha:unknown;mes:unknown;semana_desde?:unknown;semana_hasta?:unknown;totales:{moneda:string;dia:string;mes:string;semana?:string}[]};
        const amount=(v:unknown)=>typeof v==='string' && /^(?:0|[1-9][0-9]{0,30})\.[0-9]{2}$/.test(v);
        if(!value || typeof value.fecha!=='string' || !/^\d{4}-\d{2}-\d{2}$/.test(value.fecha) || value.mes!==value.fecha.slice(0,7) || !Array.isArray(value.totales) || value.totales.length>3 || new Set(value.totales.map(r=>r?.moneda)).size!==value.totales.length || value.totales.some(r=>!r || !['ARS','USD','EUR'].includes(r.moneda) || !amount(r.dia) || !amount(r.mes) || (r.semana!==undefined && !amount(r.semana)))) throw new Error();
        if((value.semana_desde!==undefined && (typeof value.semana_desde!=='string' || !/^\d{4}-\d{2}-\d{2}$/.test(value.semana_desde))) || (value.semana_hasta!==undefined && (typeof value.semana_hasta!=='string' || !/^\d{4}-\d{2}-\d{2}$/.test(value.semana_hasta))))throw new Error();
        return {fecha:value.fecha,mes:value.mes,...(value.semana_desde ? {semana_desde:value.semana_desde,semana_hasta:value.semana_hasta} : {}),totales:value.totales.map(r=>({moneda:r.moneda,dia:r.dia,mes:r.mes,...(r.semana!==undefined ? {semana:r.semana} : {})}))};
      }
      if(similarId) {
        const value=data as {referencia_id:unknown;items:unknown[]};
        if(!value || value.referencia_id!==similarId || !Array.isArray(value.items) || value.items.length>5)throw new Error();
        const items=value.items.map(item=>expense(item,space,account));
        if(items.some(item=>item.id===similarId) || new Set(items.map(item=>item.id)).size!==items.length)throw new Error();
        return {referencia_id:similarId,items};
      }
      if (suggestion) {
        const value=data as {categoria:unknown;coincidencias:unknown;total:unknown};
        if (!value || typeof value.coincidencias !== 'number' || typeof value.total !== 'number' ||
            !Number.isInteger(value.coincidencias) || !Number.isInteger(value.total) || value.total>500 || value.total<0 || value.coincidencias>value.total) throw new Error();
        if (value.categoria===null) {
          if(value.coincidencias!==0 || value.total!==0)throw new Error();
        } else if(typeof value.categoria!=='string' || !isExpenseCategory(value.categoria) || value.coincidencias<2 || value.coincidencias*3<value.total*2)throw new Error();
        return {categoria:value.categoria,coincidencias:value.coincidencias,total:value.total};
      }
      if (voidTarget) {
        const result = data as { id?: string; anulado?: boolean } | null;
        if (result?.id !== voidTarget.id || result?.anulado !== true) throw new Error();
        return { id: result.id, anulado: true };
      }
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
