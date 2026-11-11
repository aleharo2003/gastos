import { BadGatewayException, BadRequestException, Body, Controller, Get, HttpCode, HttpException, Param, Patch, Post, Query, Req, Res, UnauthorizedException } from '@nestjs/common';
import type { Request, Response } from 'express';
import { AuthService } from './auth.service.js';
import { boundedJson } from './token-verifier.js';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const CATEGORIES = ["alimentos", "transporte", "vivienda", "servicios", "salud", "educacion", "ocio", "impuestos", "auto", "bancario", "ropa", "otros"];
type ExpenseInput = { id: string; fecha: string; descripcion: string; moneda: string; importe: string; categoria?: string | null };
type Expense = ExpenseInput & { espacio_id: string; cuenta_id: string; coincidencia_aproximada?: boolean; cuenta_nombre?: string };
type ExpenseEdit = { original: ExpenseInput; nuevo: ExpenseInput };
function valid(value: unknown): value is ExpenseInput {
  const row = value as ExpenseInput;
  return !!row && (row.categoria == null || CATEGORIES.includes(row.categoria)) && typeof row.id === 'string' && UUID.test(row.id) && !/^0{8}-0{4}-0{4}-0{4}-0{12}$/.test(row.id) &&
    typeof row.fecha === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(row.fecha) &&
    typeof row.descripcion === 'string' && [...row.descripcion.trim()].length >= 1 && [...row.descripcion.trim()].length <= 160 &&
    !/[\x00-\x1f\x7f]/.test(row.descripcion) && ['ARS','USD','EUR'].includes(row.moneda) &&
    typeof row.importe === 'string' && /^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?$/.test(row.importe) && /[1-9]/.test(row.importe);
}
function expense(value: unknown, space: string, account: string | undefined): Expense {
  const row = value as Expense;
  if (row?.coincidencia_aproximada !== undefined && typeof row.coincidencia_aproximada !== 'boolean') throw new Error();
  if (row?.cuenta_nombre !== undefined && (typeof row.cuenta_nombre !== 'string' || row.cuenta_nombre.length < 1 || row.cuenta_nombre.length > 160)) throw new Error();
  if (!valid(row) || row.espacio_id !== space || (account !== undefined ? row.cuenta_id !== account : typeof row.cuenta_id !== 'string' || !UUID.test(row.cuenta_id))) throw new Error();
  return { id: row.id, espacio_id: space, cuenta_id: row.cuenta_id, fecha: row.fecha, descripcion: row.descripcion, moneda: row.moneda, importe: row.importe, ...(row.cuenta_nombre !== undefined ? {cuenta_nombre:row.cuenta_nombre} : {}), ...(row.categoria !== undefined ? {categoria:row.categoria} : {}), ...(row.coincidencia_aproximada !== undefined ? {coincidencia_aproximada:row.coincidencia_aproximada} : {}) };
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
    return this.forward(token,space,query.account as string | undefined,undefined,0,undefined,new URLSearchParams(),false,undefined,true);
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
      if (key === 'categoria' && ![...CATEGORIES,'sin_categoria'].includes(value)) throw new BadRequestException('Categoria invalida');
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
    if (!valid(body) || Object.keys(body).some(key => !['id','fecha','descripcion','moneda','importe','categoria'].includes(key))) throw new BadRequestException('Gasto invalido');
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

  @Patch('accounts/:account/expenses/:id')
  async edit(@Param('space') space: string, @Param('account') account: string, @Param('id') id: string, @Body() value: unknown, @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    response.setHeader('Cache-Control', 'no-store');
    const token = await this.token(request, response);
    const body = value as ExpenseEdit;
    if (!UUID.test(id) || !body || !valid(body.original) || !valid(body.nuevo) ||
        body.original.id.toLowerCase() !== id.toLowerCase() || body.nuevo.id.toLowerCase() !== id.toLowerCase() ||
        Object.keys(body).some(k => !['original','nuevo'].includes(k)) ||
        [body.original,body.nuevo].some(r => Object.keys(r).some(k => !['id','fecha','descripcion','moneda','importe','categoria'].includes(k)))) throw new BadRequestException('Edicion invalida');
    return this.forward(token, space, account, body, 0, id.toLowerCase());
  }

  private async forward(token: string, rawSpace: string, rawAccount: string | undefined, body?: ExpenseInput | ExpenseEdit, offset = 0, editId?: string, filters = new URLSearchParams(), suggestion = false, similarId?:string, summary = false) {
    if (!UUID.test(rawSpace) || (rawAccount !== undefined && !UUID.test(rawAccount)) || (rawAccount === undefined && !!(body || editId || suggestion || similarId))) throw new BadRequestException('Espacio invalido');
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
      const result = await fetch(new URL(summary ? `/spaces/${space}/expense-summary${account ? '?account='+account : ''}` : `/spaces/${space}${account ? '/accounts/'+account : ''}/expenses${similarId ? '/' + similarId + '/similar' : suggestion ? '/category-suggestion?' + filters.toString() : editId ? '/' + editId : '?offset=' + offset + (filters.size ? '&' + filters.toString() : '')}`, base), {
        method: editId ? 'PATCH' : body ? 'POST' : 'GET', redirect: 'error', signal: AbortSignal.timeout(timeout),
        headers: { Accept: 'application/json', Authorization: `Bearer ${token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      if ([400, 401, 403, 404, 409, 422, 503].includes(result.status)) throw new HttpException('No se pudo completar la operacion', result.status);
      if (!result.ok) throw new Error();
      const data = await boundedJson(result, 131072);
      if(summary) {
        const value=data as {fecha:unknown;mes:unknown;totales:{moneda:string;dia:string;mes:string}[]};
        const amount=(v:unknown)=>typeof v==='string' && /^(?:0|[1-9][0-9]{0,30})\.[0-9]{2}$/.test(v);
        if(!value || typeof value.fecha!=='string' || !/^\d{4}-\d{2}-\d{2}$/.test(value.fecha) || value.mes!==value.fecha.slice(0,7) || !Array.isArray(value.totales) || value.totales.length>3 || new Set(value.totales.map(r=>r?.moneda)).size!==value.totales.length || value.totales.some(r=>!r || !['ARS','USD','EUR'].includes(r.moneda) || !amount(r.dia) || !amount(r.mes))) throw new Error();
        return {fecha:value.fecha,mes:value.mes,totales:value.totales.map(r=>({moneda:r.moneda,dia:r.dia,mes:r.mes}))};
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
        } else if(typeof value.categoria!=='string' || !CATEGORIES.includes(value.categoria) || value.coincidencias<2 || value.coincidencias*3<value.total*2)throw new Error();
        return {categoria:value.categoria,coincidencias:value.coincidencias,total:value.total};
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
