import { BadGatewayException, BadRequestException, Body, Controller, Get, HttpCode, HttpException, Param, Post, Query, Req, Res, UnauthorizedException } from '@nestjs/common';
import type { Request, Response } from 'express';
import { AuthService } from './auth.service.js';
import { boundedJson } from './token-verifier.js';

const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const CATEGORIES = ['alimentos', 'transporte', 'vivienda', 'servicios', 'salud', 'educacion',
  'ocio', 'impuestos', 'auto', 'bancario', 'ropa', 'otros'];
const record=(v:unknown):v is Record<string,unknown>=>!!v && typeof v==='object' && !Array.isArray(v);
const keys=(v:Record<string,unknown>,allowed:string[])=>Object.keys(v).every(k=>allowed.includes(k));
function money(v:unknown):boolean {
  return record(v) && ['ARS','USD'].includes(v.moneda as string) && typeof v.importe==='string' && /^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?$/.test(v.importe) && /[1-9]/.test(v.importe);
}
export function validLimits(value:unknown):value is Record<'diario'|'semanal', {moneda:'ARS'|'USD';importe:string}|null> & { mensual?: { moneda:'ARS'|'USD'; importe:string } | null } {
  if(!record(value)||!keys(value,['diario','semanal','mensual']))return false;
  const periods = ['diario', 'semanal', ...('mensual' in value ? ['mensual'] : [])];
  for(const key of periods){
    const limit=value[key];
    if(limit!==null && (!money(limit)||!record(limit)||!keys(limit,['moneda','importe'])))return false;
  }
  return true;
}

function validCategoryLimits(value: unknown): boolean {
  if (!Array.isArray(value) || value.length > CATEGORIES.length) return false;
  const categories = new Set<string>();
  for (const limit of value) {
    if (!record(limit) || !keys(limit, ['categoria', 'moneda', 'importe']) || !money(limit) ||
        typeof limit.categoria !== 'string' || !CATEGORIES.includes(limit.categoria) ||
        categories.has(limit.categoria)) return false;
    categories.add(limit.categoria);
  }
  return true;
}

export function validPlan(v:unknown):boolean {
  if(!record(v)||!keys(v,['version','datos'])||!Number.isInteger(v.version)||Number(v.version)<0||Number(v.version)>2147483646||!record(v.datos))return false;
  const d=v.datos;
  if(!keys(d,['limites','conceptos','limites_categoria'])||!validLimits(d.limites)||!Array.isArray(d.conceptos)||d.conceptos.length>40)return false;
  if (d.limites_categoria !== undefined && !validCategoryLimits(d.limites_categoria)) return false;
  const seen=new Set<string>();
  for(const c of d.conceptos){
    if(!record(c)||!keys(c,['id','concepto','frecuencia','moneda','importe'])||!money(c)||typeof c.id!=='string'||!UUID.test(c.id)||seen.has(c.id.toLowerCase())||typeof c.concepto!=='string'||[...c.concepto.trim()].length<1||[...c.concepto.trim()].length>80||/[\x00-\x1f\x7f]/.test(c.concepto)||!['semana','mes'].includes(c.frecuencia as string))return false;
    seen.add(c.id.toLowerCase());
  }
  return true;
}

type PlanningResource = 'spending-plan' | 'reminder-preferences' | 'spending-plan/category-limits' | 'usd-reference' | 'usd-reference/settings' | 'usd-sales';

function validReminderPreferences(value: unknown): boolean {
  if (!record(value) || !keys(value, [
    'canal', 'dias_anticipacion', 'hora_local', 'vencimientos', 'vencidas', 'resumen_semanal',
  ])) return false;
  return (value.canal === 'ninguno' || value.canal === 'email' || value.canal === 'push') &&
    typeof value.dias_anticipacion === 'number' && Number.isInteger(value.dias_anticipacion) &&
    value.dias_anticipacion >= 0 && value.dias_anticipacion <= 30 &&
    typeof value.hora_local === 'string' && /^([01][0-9]|2[0-3]):[0-5][0-9]$/.test(value.hora_local) &&
    typeof value.vencimientos === 'boolean' && typeof value.vencidas === 'boolean' &&
    typeof value.resumen_semanal === 'boolean';
}

const rateDate = (value: unknown) => typeof value === 'string' && /^(?!0000)\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$/.test(value);
function validManualRate(value: unknown): boolean {
  return record(value) && keys(value, ['fecha', 'tasa']) && rateDate(value.fecha)
    && typeof value.tasa === 'string' && /^(?:0|[1-9][0-9]{0,7})(?:\.[0-9]{1,4})?$/.test(value.tasa)
    && /[1-9]/.test(value.tasa);
}

const saleFields = ['id','origen_id','destino_id','fecha','contraparte','usd','ars'];
const saleMoney = (value: unknown) => typeof value === 'string' && /^(?:0|[1-9][0-9]{0,11})\.[0-9]{2}$/.test(value) && value !== '0.00';
function validSaleFields(data: Record<string, unknown>): boolean {
  return [data.id,data.origen_id,data.destino_id].every(id => typeof id === 'string' && UUID.test(id))
    && data.origen_id !== data.destino_id && rateDate(data.fecha)
    && typeof data.contraparte === 'string' && data.contraparte.trim().length >= 1 && [...data.contraparte].length <= 160
    && !/[\x00-\x1f\x7f]/.test(data.contraparte) && saleMoney(data.usd) && saleMoney(data.ars);
}

function validSaleRow(data: unknown): boolean {
  return record(data) && keys(data, [...saleFields,'tasa','referencia','fecha_referencia','diferencia_pct'])
    && validSaleFields(data) && typeof data.tasa === 'string' && /^\d{1,14}\.\d{4}$/.test(data.tasa)
    && ((data.referencia === null && data.fecha_referencia === null && data.diferencia_pct === null)
      || (typeof data.referencia === 'string' && rateDate(data.fecha_referencia) && typeof data.diferencia_pct === 'string'));
}

@Controller('api/spaces/:space')
export class PlanningController {
  constructor(private readonly auth:AuthService){}
  @Get('spending-plan')
  read(@Param('space') space:string,@Req() request:Request,@Res({passthrough:true}) response:Response){return this.forward(space,request,response);}
  @Get('spending-plan/category-limits')
  readCategoryLimits(
    @Param('space') space: string, @Query('mes') month: unknown,
    @Req() request: Request, @Res({ passthrough: true }) response: Response,
  ) {
    return this.forward(space, request, response, undefined, false, 'spending-plan/category-limits', month);
  }
  @Post('spending-plan')
  @HttpCode(200)
  save(@Param('space') space:string,@Body() body:unknown,@Req() request:Request,@Res({passthrough:true}) response:Response){return this.forward(space,request,response,body,true);}
  @Get('reminder-preferences')
  readReminderPreferences(
    @Param('space') space: string, @Req() request: Request, @Res({ passthrough: true }) response: Response,
  ) {
    return this.forward(space, request, response, undefined, false, 'reminder-preferences');
  }

  @Post('reminder-preferences')
  @HttpCode(200)
  saveReminderPreferences(
    @Param('space') space: string, @Body() body: unknown,
    @Req() request: Request, @Res({ passthrough: true }) response: Response,
  ) {
    return this.forward(space, request, response, body, true, 'reminder-preferences');
  }

  @Get('usd-reference')
  readUsdReference(
    @Param('space') space: string, @Query('fecha') date: unknown,
    @Req() request: Request, @Res({ passthrough: true }) response: Response,
  ) {
    return this.forward(space, request, response, undefined, false, 'usd-reference', date);
  }

  @Post('usd-reference')
  @HttpCode(200)
  saveUsdReference(
    @Param('space') space: string, @Body() body: unknown,
    @Req() request: Request, @Res({ passthrough: true }) response: Response,
  ) {
    return this.forward(space, request, response, body, true, 'usd-reference');
  }

  @Get('usd-reference/settings')
  readMarketType(@Param('space') space: string, @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    return this.forward(space, request, response, undefined, false, 'usd-reference/settings');
  }

  @Post('usd-reference/settings')
  @HttpCode(200)
  saveMarketType(@Param('space') space: string, @Body() body: unknown, @Req() request: Request,
    @Res({ passthrough: true }) response: Response) {
    return this.forward(space, request, response, body, true, 'usd-reference/settings');
  }

  @Get('usd-sales')
  readUsdSales(@Param('space') space: string, @Query('offset') offset: unknown,
    @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    return this.forward(space, request, response, undefined, false, 'usd-sales', offset);
  }

  @Post('usd-sales')
  @HttpCode(200)
  saveUsdSale(@Param('space') space: string, @Body() body: unknown,
    @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    return this.forward(space, request, response, body, true, 'usd-sales');
  }

  private async forward(
    space: string, request: Request, response: Response, body?: unknown,
    writing = false, resource: PlanningResource = 'spending-plan', month?: unknown,
  ) {
    response.setHeader('Cache-Control','no-store');
    const count=request.rawHeaders.filter((v,i)=>i%2===0&&v.toLowerCase()==='authorization').length;
    const parts=request.headers.authorization?.trim().split(/\s+/)??[];
    try {
      if(count!==1||parts.length!==2||parts[0].toLowerCase()!=='bearer')throw new UnauthorizedException('No autenticado');
      await this.auth.verifyIdentity(parts[1]);
    } catch(error){if(error instanceof UnauthorizedException)response.setHeader('WWW-Authenticate','Bearer');throw error;}
    const history = resource === 'spending-plan/category-limits';
    const usd = resource === 'usd-reference';
    const market = resource === 'usd-reference/settings';
    const sale = resource === 'usd-sales';
    const validate = sale ? (data: unknown) => writing ? validSaleRow(data) :
      record(data) && keys(data, ['items','next_offset']) && Array.isArray(data.items) && data.items.length <= 100
      && data.items.every(validSaleRow) && (data.next_offset === null || data.next_offset === Number(month ?? 0) + 100)
      : market ? (data: unknown) => record(data) && keys(data, ['tipo']) &&
      typeof data.tipo === 'string' && ['oficial', 'blue', 'bolsa', 'contadoconliqui', 'mayorista', 'cripto', 'tarjeta'].includes(data.tipo)
      : history
      ? (data: unknown) => record(data) && keys(data, ['mes', 'limites_categoria']) &&
          data.mes === month && (data.limites_categoria === null || validCategoryLimits(data.limites_categoria))
      : usd ? (data: unknown) => record(data) && keys(data, ['cotizacion']) &&
          (data.cotizacion === null || validManualRate(data.cotizacion))
        : resource === 'spending-plan' ? validPlan : validReminderPreferences;
    if (!UUID.test(space) || (writing && !(sale ? record(body) && keys(body, saleFields) && validSaleFields(body) : usd ? validManualRate(body) : validate(body))) ||
        (sale && month !== undefined && (typeof month !== 'string' || !/^\d{1,6}$/.test(month) || Number(month) > 100000)) ||
        (usd && month !== undefined && !rateDate(month)) ||
        (history && (typeof month !== 'string' || !/^(19[0-9]{2}|20[0-9]{2})-(0[1-9]|1[0-2])$/.test(month)))) {
      throw new BadRequestException(sale ? 'Venta inválida' : history ? 'Mes o espacio invalido'
        : usd ? 'Cotización inválida' : resource === 'spending-plan' ? 'Presupuesto invalido' : 'Preferencias invalidas');
    }
    try {
      const base=new URL(process.env.API_BASE_URL??'http://127.0.0.1:8000');
      const local=['localhost','127.0.0.1','[::1]','api'].includes(base.hostname);
      if(base.username||base.password||base.search||base.hash||base.pathname!=='/'||(base.protocol!=='https:'&&!(base.protocol==='http:'&&local)))throw new Error();
      const raw=process.env.API_TIMEOUT_MS??'5000',timeout=Number(raw);
      if(!/^\d+$/.test(raw)||!Number.isSafeInteger(timeout)||timeout<1||timeout>2147483647)throw new Error();
      const url = new URL(`/spaces/${space.toLowerCase()}/${resource}`, base);
      if (history) url.searchParams.set('mes', String(month));
      if (sale && month !== undefined) url.searchParams.set('offset', String(month));
      if (usd && month !== undefined) url.searchParams.set('fecha', String(month));
      const result=await fetch(url,{
        method:writing?(resource==='reminder-preferences'?'PUT':'POST'):'GET',redirect:'error',signal:AbortSignal.timeout(timeout),
        headers:{Accept:'application/json',Authorization:`Bearer ${parts[1]}`,...(writing?{'Content-Type':'application/json'}:{})},
        ...(writing?{body:JSON.stringify(body)}:{}),
      });
      if([400,401,403,409,422,503].includes(result.status))throw new HttpException('No se pudo completar la operacion',result.status);
      if(!result.ok)throw new Error();
      const data=await boundedJson(result,65536);
      if(!validate(data))throw new Error();
      return data;
    } catch(error){if(error instanceof HttpException)throw error;throw new BadGatewayException('No se pudo consultar FastAPI');}
  }
}
