import { BadGatewayException, BadRequestException, Body, Controller, Get, HttpCode, HttpException, Param, Post, Query, Req, Res, UnauthorizedException } from '@nestjs/common';
import type { Request, Response } from 'express';
import { AuthService } from './auth.service.js';
import { boundedJson } from './token-verifier.js';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const INCOME_CATEGORIES = new Set(['sueldo', 'honorarios', 'venta', 'regalo', 'reintegro', 'otros_ingresos']);
type IncomeInput = { id:string; fecha:string; descripcion:string; moneda:string; importe:string; categoria?: string | null };
type Income = IncomeInput & {espacio_id:string; cuenta_id:string; cuenta_nombre?: string };
function valid(value: unknown): value is IncomeInput {
  const row = value as IncomeInput;
  return !!row && (row.categoria == null || (typeof row.categoria === 'string' &&
    (INCOME_CATEGORIES.has(row.categoria) || UUID.test(row.categoria)))) &&
    typeof row.id === 'string' && UUID.test(row.id) && !/^0{8}-0{4}-0{4}-0{4}-0{12}$/.test(row.id) &&
    typeof row.fecha === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(row.fecha) &&
    typeof row.descripcion === 'string' && [...row.descripcion.trim()].length >= 1 && [...row.descripcion.trim()].length <= 160 &&
    !/[\x00-\x1f\x7f]/.test(row.descripcion) && ['ARS','USD','EUR'].includes(row.moneda) &&
    typeof row.importe === 'string' && /^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?$/.test(row.importe) && /[1-9]/.test(row.importe);
}

function income(value:unknown, space:string, account?:string):Income {
  const row=value as Income;
  if(!valid(row) || row.espacio_id!==space || !UUID.test(row.cuenta_id) ||
      (account!==undefined && row.cuenta_id!==account)) throw new Error();
  if (row.cuenta_nombre !== undefined && (typeof row.cuenta_nombre !== 'string' || row.cuenta_nombre.length > 160)) throw new Error();
  return {id:row.id,espacio_id:space,cuenta_id:row.cuenta_id,fecha:row.fecha,
    descripcion:row.descripcion,moneda:row.moneda,importe:row.importe,
    ...(row.categoria == null ? {} : { categoria: row.categoria }),
    ...(row.cuenta_nombre === undefined ? {} : { cuenta_nombre: row.cuenta_nombre })};
}
export function validateBalance(value:unknown) {
  const data=value as {totales:{moneda:string;ingresos:string;gastos:string;saldo:string;transferencias_entrada?:string;transferencias_salida?:string}[]};
  if(!data || !Array.isArray(data.totales) || data.totales.length!==3)throw new Error();
  const seen=new Set<string>();
  const totales=data.totales.map(row=>{
    if(!row || !['ARS','USD','EUR'].includes(row.moneda) || seen.has(row.moneda))throw new Error();
    seen.add(row.moneda);
    const incoming=row.transferencias_entrada===undefined?'0.00':row.transferencias_entrada,outgoing=row.transferencias_salida===undefined?'0.00':row.transferencias_salida;
    for(const value of [incoming,outgoing]){
      if(typeof value!=='string'||value.length>80||!/^(?:0|[1-9][0-9]*)\.[0-9]{2}$/.test(value))throw new Error();
    }
    for(const key of ['ingresos','gastos','saldo'] as const) {
      if(typeof row[key]!=='string' || row[key].length>80 ||
          !(key==='saldo' ? /^-?(?:0|[1-9][0-9]*)\.[0-9]{2}$/ : /^(?:0|[1-9][0-9]*)\.[0-9]{2}$/).test(row[key]))throw new Error();
    }
    const cents=(v:string)=>BigInt(v.replace('.',''));
    if(cents(row.ingresos)-cents(row.gastos)+cents(incoming)-cents(outgoing)!==cents(row.saldo))throw new Error();
    return {moneda:row.moneda,ingresos:row.ingresos,gastos:row.gastos,saldo:row.saldo,...(row.transferencias_entrada!==undefined?{transferencias_entrada:incoming}:{}),...(row.transferencias_salida!==undefined?{transferencias_salida:outgoing}:{})};
  });
  return {totales};
}

@Controller('api/spaces/:space')
export class IncomesController {
  constructor(private readonly auth:AuthService) {}

  @Get('incomes')
  async all(@Param('space') space:string, @Query() query:Record<string,unknown>, @Req() request:Request, @Res({passthrough:true}) response:Response) {
    return this.list(space,undefined,query,request,response);
  }

  @Get('accounts/:account/incomes')
  async list(@Param('space') space:string, @Param('account') account:string|undefined, @Query() query:Record<string,unknown>, @Req() request:Request, @Res({passthrough:true}) response:Response) {
    response.setHeader('Cache-Control','no-store');
    const token=await this.token(request,response);
    if(Object.keys(query).some(k=>k!=='offset') || (query.offset!==undefined &&
      (typeof query.offset!=='string' || !/^\d{1,6}$/.test(query.offset) || Number(query.offset)>100000)))throw new BadRequestException('Pagina invalida');
    return this.forward(token,space,account,'list',undefined,Number(query.offset??0));
  }

  @Post('accounts/:account/incomes')
  @HttpCode(200)
  async create(@Param('space') space:string, @Param('account') account:string, @Body() body:unknown, @Req() request:Request, @Res({passthrough:true}) response:Response) {
    response.setHeader('Cache-Control','no-store');
    const token=await this.token(request,response);
    if(!valid(body) || Object.keys(body).some(k=>!['id','fecha','descripcion','moneda','importe','categoria'].includes(k)))throw new BadRequestException('Ingreso invalido');
    return this.forward(token,space,account,'create',{...body,id:body.id.toLowerCase(),descripcion:body.descripcion.trim()});
  }

  @Get('account-balance')
  async summary(@Param('space') space:string, @Query() query:Record<string,unknown>, @Req() request:Request, @Res({passthrough:true}) response:Response) {
    response.setHeader('Cache-Control','no-store');
    const token=await this.token(request,response);
    if(Object.keys(query).some(k=>k!=='account') || (query.account!==undefined && typeof query.account!=='string'))throw new BadRequestException('Cuenta invalida');
    return this.forward(token,space,query.account as string|undefined,'balance');
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


  private async forward(token:string, rawSpace:string, rawAccount:string|undefined, operation:'list'|'create'|'balance', body?:IncomeInput, offset=0) {
    if(!UUID.test(rawSpace) || (rawAccount!==undefined && !UUID.test(rawAccount)))throw new BadRequestException('Espacio o cuenta invalida');
    const space=rawSpace.toLowerCase(), account=rawAccount?.toLowerCase();
    try {
      const base=new URL(process.env.API_BASE_URL??'http://127.0.0.1:8000');
      const local=['localhost','127.0.0.1','[::1]','api'].includes(base.hostname);
      if(base.username || base.password || base.search || base.hash || base.pathname!=='/' ||
          (base.protocol!=='https:' && !(base.protocol==='http:' && local)))throw new Error();
      const rawTimeout=process.env.API_TIMEOUT_MS??'5000',timeout=Number(rawTimeout);
      if(!/^\d+$/.test(rawTimeout) || !Number.isSafeInteger(timeout) || timeout<1 || timeout>2147483647)throw new Error();
      const path=operation==='balance'
        ? `/spaces/${space}/account-balance${account?'?account='+account:''}`
        : `/spaces/${space}${account?'/accounts/'+account:''}/incomes?offset=${offset}`;
      const result=await fetch(new URL(path,base),{
        method:body?'POST':'GET',redirect:'error',signal:AbortSignal.timeout(timeout),
        headers:{Accept:'application/json',Authorization:`Bearer ${token}`,...(body?{'Content-Type':'application/json'}:{})},
        ...(body?{body:JSON.stringify(body)}:{})
      });
      if([400,401,403,404,409,422,503].includes(result.status))throw new HttpException('No se pudo completar la operacion',result.status);
      if(!result.ok)throw new Error();
      const data=await boundedJson(result,131072);
      if(operation==='balance')return validateBalance(data);
      if(body)return income(data,space,account);
      const page=data as {items:unknown[];next_offset:number|null};
      if(!page || !Array.isArray(page.items) || page.items.length>100 ||
          !(page.next_offset===null || page.next_offset===offset+100))throw new Error();
      return {items:page.items.map(row=>income(row,space,account)),next_offset:page.next_offset};
    } catch(error) {
      if(error instanceof HttpException)throw error;
      throw new BadGatewayException('No se pudo consultar FastAPI');
    }
  }
}
