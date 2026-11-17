import { BadGatewayException,BadRequestException,Body,Controller,Get,HttpCode,HttpException,Param,Patch,Post,Query,Req,Res,UnauthorizedException } from '@nestjs/common';
import type { Request,Response } from 'express';
import { AuthService } from './auth.service.js';
import { boundedJson } from './token-verifier.js';

const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const nonzero=(v:unknown):v is string=>typeof v==='string'&&UUID.test(v)&&!/^0{8}-0{4}-0{4}-0{4}-0{12}$/.test(v);
type Fields={nombre:string;objetivo:string;fecha_objetivo:string|null};
type Create=Fields & {id:string;cuenta_id:string;moneda:string};
type Edit=Fields & {version:number;archivada:boolean};
type Goal=Create & {espacio_id:string;cuenta_nombre:string;archivada:boolean;version:number;saldo:string;acumulado:string;faltante:string;porcentaje:string;alcanzada:boolean;vencida:boolean};
function fields(value:unknown):value is Fields {
  const row=value as Fields;
  return !!row&&typeof row.nombre==='string'&&[...row.nombre.trim()].length>=1&&[...row.nombre.trim()].length<=160&&
    !/[\x00-\x1f\x7f]/.test(row.nombre)&&typeof row.objetivo==='string'&&
    /^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?$/.test(row.objetivo)&&/[1-9]/.test(row.objetivo)&&
    (row.fecha_objetivo===null||(typeof row.fecha_objetivo==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(row.fecha_objetivo)));
}
const validCreate=(v:unknown):v is Create=>{
  const row=v as Create;return fields(row)&&nonzero(row.id)&&nonzero(row.cuenta_id)&&['ARS','USD','EUR'].includes(row.moneda);
};
const validEdit=(v:unknown):v is Edit=>{
  const row=v as Edit;return fields(row)&&Number.isInteger(row.version)&&row.version>=0&&row.version<=2147483646&&typeof row.archivada==='boolean';
};
const normalized=(v:string)=>{const [whole,fraction='']=v.split('.');return whole+'.'+fraction.padEnd(2,'0');};
function goal(value:unknown,space:string):Goal {
  const row=value as Goal;
  if(!validCreate(row)||row.espacio_id!==space||typeof row.cuenta_nombre!=='string'||!row.cuenta_nombre||
      row.cuenta_nombre.length>160||!Number.isInteger(row.version)||row.version<0||row.version>2147483647||
      typeof row.archivada!=='boolean'||typeof row.alcanzada!=='boolean'||typeof row.vencida!=='boolean')throw new Error();
  for(const key of ['saldo','acumulado','faltante'] as const){
    if(typeof row[key]!=='string'||row[key].length>40||
      !(key==='saldo'?/^-?(?:0|[1-9][0-9]*)\.[0-9]{2}$/:/^(?:0|[1-9][0-9]*)\.[0-9]{2}$/).test(row[key]))throw new Error();
  }
  if(typeof row.porcentaje!=='string'||! /^(?:100\.0|[0-9]{1,2}\.[0-9])$/.test(row.porcentaje))throw new Error();
  const cents=(s:string)=>BigInt(normalized(s).replace('.',''));
  const saldo=cents(row.saldo),saved=saldo>0n?saldo:0n,target=cents(row.objetivo),remaining=target>saved?target-saved:0n;
  if(cents(row.acumulado)!==saved||cents(row.faltante)!==remaining||row.alcanzada!==(saved>=target)||
      BigInt(row.porcentaje.replace('.',''))!==(saved>target?target:saved)*1000n/target)throw new Error();
  return {id:row.id,espacio_id:space,cuenta_id:row.cuenta_id,cuenta_nombre:row.cuenta_nombre,nombre:row.nombre,
    moneda:row.moneda,objetivo:row.objetivo,fecha_objetivo:row.fecha_objetivo,archivada:row.archivada,version:row.version,
    saldo:row.saldo,acumulado:row.acumulado,faltante:row.faltante,porcentaje:row.porcentaje,alcanzada:row.alcanzada,vencida:row.vencida};
}

@Controller('api/spaces/:space/savings-goals')
export class SavingsGoalsController {
  constructor(private readonly auth:AuthService){}

  @Get()
  async list(@Param('space') space:string,@Query() query:Record<string,unknown>,@Req() request:Request,@Res({passthrough:true}) response:Response){
    response.setHeader('Cache-Control','no-store');const token=await this.token(request,response);
    if(Object.keys(query).some(k=>!['offset','archived'].includes(k))||
      (query.offset!==undefined&&(typeof query.offset!=='string'||!/^\d{1,6}$/.test(query.offset)||Number(query.offset)>100000))||
      (query.archived!==undefined&&!['true','false'].includes(query.archived as string)))throw new BadRequestException('Filtro invalido');
    return this.forward(token,space,'GET',undefined,undefined,Number(query.offset??0),query.archived==='true');
  }

  @Post()
  @HttpCode(200)
  async create(@Param('space') space:string,@Body() body:unknown,@Req() request:Request,@Res({passthrough:true}) response:Response){
    response.setHeader('Cache-Control','no-store');const token=await this.token(request,response);
    if(!validCreate(body)||Object.keys(body).some(k=>!['id','cuenta_id','nombre','moneda','objetivo','fecha_objetivo'].includes(k)))throw new BadRequestException('Meta invalida');
    return this.forward(token,space,'POST',{...body,id:body.id.toLowerCase(),cuenta_id:body.cuenta_id.toLowerCase(),nombre:body.nombre.trim()});
  }

  @Patch(':id')
  async edit(@Param('space') space:string,@Param('id') id:string,@Body() body:unknown,@Req() request:Request,@Res({passthrough:true}) response:Response){
    response.setHeader('Cache-Control','no-store');const token=await this.token(request,response);
    if(!nonzero(id)||!validEdit(body)||Object.keys(body).some(k=>!['nombre','objetivo','fecha_objetivo','version','archivada'].includes(k)))throw new BadRequestException('Edicion invalida');
    return this.forward(token,space,'PATCH',{...body,nombre:body.nombre.trim()},id.toLowerCase());
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




  private async forward(token:string,rawSpace:string,method:'GET'|'POST'|'PATCH',body?:Create|Edit,id?:string,offset=0,archived=false){
    if(!UUID.test(rawSpace))throw new BadRequestException('Espacio invalido');
    const space=rawSpace.toLowerCase();
    try{
      const base=new URL(process.env.API_BASE_URL??'http://127.0.0.1:8000');
      const local=['localhost','127.0.0.1','[::1]','api'].includes(base.hostname);
      if(base.username||base.password||base.search||base.hash||base.pathname!=='/'||(base.protocol!=='https:'&&!(base.protocol==='http:'&&local)))throw new Error();
      const rawTimeout=process.env.API_TIMEOUT_MS??'5000',timeout=Number(rawTimeout);
      if(!/^\d+$/.test(rawTimeout)||!Number.isSafeInteger(timeout)||timeout<1||timeout>2147483647)throw new Error();
      const path=`/spaces/${space}/savings-goals${id?'/'+id:''}${method==='GET'?'?offset='+offset+'&archived='+archived:''}`;
      const result=await fetch(new URL(path,base),{method,redirect:'error',signal:AbortSignal.timeout(timeout),
        headers:{Accept:'application/json',Authorization:`Bearer ${token}`,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});
      if([400,401,403,404,409,422,503].includes(result.status))throw new HttpException('No se pudo completar la operacion',result.status);
      if(!result.ok)throw new Error();
      const data=await boundedJson(result,262144);
      if(body){
        const row=goal(data,space);
        if(row.nombre!==body.nombre||normalized(row.objetivo)!==normalized(body.objetivo)||row.fecha_objetivo!==body.fecha_objetivo)throw new Error();
        if(method==='PATCH'){
          const edit=body as Edit;if(row.id!==id||row.archivada!==edit.archivada||row.version!==edit.version+1)throw new Error();
        }else{
          const create=body as Create;if(row.id!==create.id||row.cuenta_id!==create.cuenta_id||row.moneda!==create.moneda||row.archivada)throw new Error();
        }
        return row;
      }
      const page=data as {items:unknown[];next_offset:number|null};
      if(!page||!Array.isArray(page.items)||page.items.length>100||!(page.next_offset===null||page.next_offset===offset+100))throw new Error();
      const items=page.items.map(row=>goal(row,space));
      if(!archived&&items.some(row=>row.archivada))throw new Error();
      return {items,next_offset:page.next_offset};
    }catch(error){if(error instanceof HttpException)throw error;throw new BadGatewayException('No se pudo consultar FastAPI');}
  }
}
