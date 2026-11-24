import { BadGatewayException, BadRequestException, Body, Controller, Get, HttpCode, HttpException, Param, Post, Req, Res, UnauthorizedException } from '@nestjs/common';
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
export function validLimits(value:unknown):value is Record<'diario'|'semanal', {moneda:'ARS'|'USD';importe:string}|null> {
  if(!record(value)||!keys(value,['diario','semanal']))return false;
  for(const key of ['diario','semanal']){
    const limit=value[key];
    if(limit!==null && (!money(limit)||!record(limit)||!keys(limit,['moneda','importe'])))return false;
  }
  return true;
}

export function validPlan(v:unknown):boolean {
  if(!record(v)||!keys(v,['version','datos'])||!Number.isInteger(v.version)||Number(v.version)<0||Number(v.version)>2147483646||!record(v.datos))return false;
  const d=v.datos;
  if(!keys(d,['limites','conceptos','limites_categoria'])||!validLimits(d.limites)||!Array.isArray(d.conceptos)||d.conceptos.length>40)return false;
  if (d.limites_categoria !== undefined) {
    if (!Array.isArray(d.limites_categoria) || d.limites_categoria.length > CATEGORIES.length) return false;
    const categories = new Set<string>();
    for (const limit of d.limites_categoria) {
      if (!record(limit) || !keys(limit, ['categoria', 'moneda', 'importe']) || !money(limit) ||
          typeof limit.categoria !== 'string' || !CATEGORIES.includes(limit.categoria) ||
          categories.has(limit.categoria)) return false;
      categories.add(limit.categoria);
    }
  }
  const seen=new Set<string>();
  for(const c of d.conceptos){
    if(!record(c)||!keys(c,['id','concepto','frecuencia','moneda','importe'])||!money(c)||typeof c.id!=='string'||!UUID.test(c.id)||seen.has(c.id.toLowerCase())||typeof c.concepto!=='string'||[...c.concepto.trim()].length<1||[...c.concepto.trim()].length>80||/[\x00-\x1f\x7f]/.test(c.concepto)||!['semana','mes'].includes(c.frecuencia as string))return false;
    seen.add(c.id.toLowerCase());
  }
  return true;
}

type PlanningResource = 'spending-plan' | 'reminder-preferences';

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

@Controller('api/spaces/:space')
export class PlanningController {
  constructor(private readonly auth:AuthService){}
  @Get('spending-plan')
  read(@Param('space') space:string,@Req() request:Request,@Res({passthrough:true}) response:Response){return this.forward(space,request,response);}
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

  private async forward(
    space: string, request: Request, response: Response, body?: unknown,
    writing = false, resource: PlanningResource = 'spending-plan',
  ) {
    response.setHeader('Cache-Control','no-store');
    const count=request.rawHeaders.filter((v,i)=>i%2===0&&v.toLowerCase()==='authorization').length;
    const parts=request.headers.authorization?.trim().split(/\s+/)??[];
    try {
      if(count!==1||parts.length!==2||parts[0].toLowerCase()!=='bearer')throw new UnauthorizedException('No autenticado');
      await this.auth.verifyIdentity(parts[1]);
    } catch(error){if(error instanceof UnauthorizedException)response.setHeader('WWW-Authenticate','Bearer');throw error;}
    const validate = resource === 'spending-plan' ? validPlan : validReminderPreferences;
    if (!UUID.test(space) || (writing && !validate(body))) {
      throw new BadRequestException(resource === 'spending-plan' ? 'Presupuesto invalido' : 'Preferencias invalidas');
    }
    try {
      const base=new URL(process.env.API_BASE_URL??'http://127.0.0.1:8000');
      const local=['localhost','127.0.0.1','[::1]','api'].includes(base.hostname);
      if(base.username||base.password||base.search||base.hash||base.pathname!=='/'||(base.protocol!=='https:'&&!(base.protocol==='http:'&&local)))throw new Error();
      const raw=process.env.API_TIMEOUT_MS??'5000',timeout=Number(raw);
      if(!/^\d+$/.test(raw)||!Number.isSafeInteger(timeout)||timeout<1||timeout>2147483647)throw new Error();
      const result=await fetch(new URL(`/spaces/${space.toLowerCase()}/${resource}`,base),{
        method:writing?(resource==='spending-plan'?'POST':'PUT'):'GET',redirect:'error',signal:AbortSignal.timeout(timeout),
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
