import { BadGatewayException,BadRequestException,Body,Controller,Get,HttpCode,HttpException,Param,Patch,Post,Query,Req,Res,UnauthorizedException } from '@nestjs/common';
import type { Request,Response } from 'express';
import { AuthService } from './auth.service.js';
import { boundedJson } from './token-verifier.js';
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const validId=(v:unknown):v is string=>typeof v==='string'&&UUID.test(v)&&!/^0{8}-0{4}-0{4}-0{4}-0{12}$/.test(v);
const date=(v:unknown):v is string=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v);
const currencies=['ARS','USD','EUR'];
const categories=['alimentos','transporte','vivienda','servicios','salud','educacion','ocio','impuestos','auto','bancario','ropa','otros'];
const amount=(v:unknown):v is string=>typeof v==='string'&&/^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?$/.test(v)&&/[1-9]/.test(v);
const sum=(v:unknown):v is string=>typeof v==='string'&&v.length<=40&&/^(?:0|[1-9][0-9]*)\.[0-9]{2}$/.test(v);
const cents=(v:string)=>{const [whole,fraction='']=v.split('.');return BigInt(whole)*100n+BigInt(fraction.padEnd(2,'0'));};
type Create={id:string;cuenta_id:string;nombre:string;moneda:string;importe:string;categoria?:string|null;primer_vencimiento:string;total_cuotas:number|null};
type Pay={id:string;cuenta_id:string;fecha:string;importe:string};
type Commitment=Create & {pausado:boolean;version:number;espacio_id:string;cuotas_pagadas:number;total:string;pagado:string;pendiente:string;proximo_vencimiento:string|null};
type Installment={id:string;espacio_id:string;compromiso_id:string;numero:number;vencimiento:string;importe:string;pagado:string;pendiente:string;estado:string;vencida:boolean};
type Payment=Pay & {espacio_id:string;cuota_id:string;moneda:string};
function validCreate(v:unknown):v is Create{
  const r=v as Create;
  return !!r&&validId(r.id)&&validId(r.cuenta_id)&&typeof r.nombre==='string'&&[...r.nombre.trim()].length>=1&&[...r.nombre.trim()].length<=160&&
    !/[\x00-\x1f\x7f]/.test(r.nombre)&&currencies.includes(r.moneda)&&amount(r.importe)&&date(r.primer_vencimiento)&&
    (r.total_cuotas===null||(Number.isInteger(r.total_cuotas)&&r.total_cuotas>=1&&r.total_cuotas<=600))&&(r.categoria==null||categories.includes(r.categoria));
}
function validPay(v:unknown):v is Pay{
  const r=v as Pay;return !!r&&validId(r.id)&&validId(r.cuenta_id)&&date(r.fecha)&&amount(r.importe);
}
function commitment(v:unknown,space:string):Commitment{
  const r=v as Commitment;
  if(!validCreate(r)||r.espacio_id!==space||!Number.isInteger(r.cuotas_pagadas)||r.cuotas_pagadas<0||(r.total_cuotas!==null&&r.cuotas_pagadas>r.total_cuotas)||typeof r.pausado!=='boolean'||!Number.isSafeInteger(r.version)||r.version<1||
    !sum(r.total)||!sum(r.pagado)||!sum(r.pendiente)||(r.total_cuotas!==null&&cents(r.total)!==cents(r.importe)*BigInt(r.total_cuotas))||
    cents(r.pagado)+cents(r.pendiente)!==cents(r.total)||!(r.proximo_vencimiento===null||date(r.proximo_vencimiento))||
    (cents(r.pendiente)===0n)!==(r.proximo_vencimiento===null)||BigInt(r.cuotas_pagadas)*cents(r.importe)>cents(r.pagado))throw new Error();
  return {id:r.id,espacio_id:space,cuenta_id:r.cuenta_id,nombre:r.nombre,moneda:r.moneda,importe:r.importe,categoria:r.categoria??null,
    primer_vencimiento:r.primer_vencimiento,total_cuotas:r.total_cuotas,pausado:r.pausado,version:r.version,cuotas_pagadas:r.cuotas_pagadas,total:r.total,pagado:r.pagado,pendiente:r.pendiente,proximo_vencimiento:r.proximo_vencimiento};
}
function installment(v:unknown,space:string,id:string):Installment{
  const r=v as Installment;
  if(!r||!validId(r.id)||r.espacio_id!==space||r.compromiso_id!==id||!Number.isInteger(r.numero)||r.numero<1||r.numero>119988||
    !date(r.vencimiento)||!amount(r.importe)||!sum(r.pagado)||!sum(r.pendiente)||cents(r.pagado)+cents(r.pendiente)!==cents(r.importe)||
    r.estado!==(cents(r.pendiente)===0n?'pagada':cents(r.pagado)>0n?'parcial':'pendiente')||typeof r.vencida!=='boolean'||(r.estado==='pagada'&&r.vencida))throw new Error();
  return {id:r.id,espacio_id:space,compromiso_id:id,numero:r.numero,vencimiento:r.vencimiento,importe:r.importe,pagado:r.pagado,pendiente:r.pendiente,estado:r.estado,vencida:r.vencida};
}
function payment(v:unknown,space:string,id:string):Payment{
  const r=v as Payment;if(!validPay(r)||r.espacio_id!==space||r.cuota_id!==id||!currencies.includes(r.moneda))throw new Error();
  return {id:r.id,espacio_id:space,cuota_id:id,cuenta_id:r.cuenta_id,fecha:r.fecha,moneda:r.moneda,importe:r.importe};
}
type MonthlyItem=Installment & {nombre:string;moneda:string;cuenta_id:string};
type MonthlyTotal={moneda:string;cuotas:number;cuotas_pagadas:number;total:string;pagado:string;pendiente:string;vencido:string};
function validMonth(value:unknown):value is string{
  return typeof value==='string'&&/^[0-9]{4}-(0[1-9]|1[0-2])$/.test(value)&&!value.startsWith('0000');
}
function monthlyPage(value:unknown,space:string,month:string,offset:number){
  const page=value as {mes:string;items:MonthlyItem[];totales:MonthlyTotal[];next_offset:number|null};
  if(!page||page.mes!==month||!Array.isArray(page.items)||page.items.length>100||!Array.isArray(page.totales)||page.totales.length>3||
    !(page.next_offset===null||page.next_offset===offset+100))throw new Error();
  const seen=new Set<string>();
  const totales=page.totales.map(t=>{
    if(!t||!currencies.includes(t.moneda)||seen.has(t.moneda)||!Number.isSafeInteger(t.cuotas)||t.cuotas<1||
      !Number.isSafeInteger(t.cuotas_pagadas)||t.cuotas_pagadas<0||t.cuotas_pagadas>t.cuotas||
      !sum(t.total)||!sum(t.pagado)||!sum(t.pendiente)||!sum(t.vencido)||
      cents(t.total)!==cents(t.pagado)+cents(t.pendiente)||cents(t.vencido)>cents(t.pendiente))throw new Error();
    seen.add(t.moneda);return {moneda:t.moneda,cuotas:t.cuotas,cuotas_pagadas:t.cuotas_pagadas,total:t.total,pagado:t.pagado,pendiente:t.pendiente,vencido:t.vencido};
  });
  const ids=new Set<string>();
  const items=page.items.map(t=>{
    if(!t||!validId(t.compromiso_id)||!validId(t.cuenta_id)||typeof t.nombre!=='string'||!t.nombre.trim()||
      [...t.nombre].length>160||!seen.has(t.moneda)||typeof t.vencimiento!=='string'||!t.vencimiento.startsWith(month+'-')||ids.has(t.id))throw new Error();
    const row=installment(t,space,t.compromiso_id);ids.add(row.id);
    return {...row,nombre:t.nombre,moneda:t.moneda,cuenta_id:t.cuenta_id};
  });
  return {mes:month,items,totales,next_offset:page.next_offset};
}
@Controller('api/spaces/:space')
export class CommitmentsController{
  constructor(private readonly auth:AuthService){}
  @Get('installments')
  async monthly(@Param('space') space:string,@Query() query:Record<string,unknown>,@Req() req:Request,@Res({passthrough:true}) res:Response){
    res.setHeader('Cache-Control','no-store');const token=await this.token(req,res);
    if(!validMonth(query.month)||Object.keys(query).some(k=>!['month','offset'].includes(k))||
      (query.offset!==undefined&&(typeof query.offset!=='string'||!/^\d{1,6}$/.test(query.offset)||Number(query.offset)>100000)))throw new BadRequestException('Mes o pagina invalida');
    return this.forward(token,space,'monthly',undefined,Number(query.offset??0),undefined,query.month);
  }
  @Patch('commitments/:id')
  async pause(@Param('space') space:string,@Param('id') id:string,@Body() body:unknown,@Req() req:Request,@Res({passthrough:true}) res:Response){
    res.setHeader('Cache-Control','no-store');const token=await this.token(req,res);
    const value=body as {pausado:boolean;version:number};
    if(!validId(id)||!value||typeof value.pausado!=='boolean'||!Number.isInteger(value.version)||value.version<1||value.version>2147483646||
      Object.keys(value).some(k=>!['pausado','version'].includes(k)))throw new BadRequestException('Pausa invalida');
    return this.forward(token,space,'pause',id.toLowerCase(),0,value);
  }
  @Get('commitments/:id')
  async detail(@Param('space') space:string,@Param('id') id:string,@Req() req:Request,@Res({passthrough:true}) res:Response){
    res.setHeader('Cache-Control','no-store');const token=await this.token(req,res);
    if(!validId(id))throw new BadRequestException('Compromiso invalido');
    return this.forward(token,space,'detail',id.toLowerCase());
  }
  @Get('commitments')
  async list(@Param('space') space:string,@Query() query:Record<string,unknown>,@Req() req:Request,@Res({passthrough:true}) res:Response){
    return this.read(space,'commitments',undefined,query,req,res);
  }
  @Get('commitments/:id/installments')
  async installments(@Param('space') space:string,@Param('id') id:string,@Query() query:Record<string,unknown>,@Req() req:Request,@Res({passthrough:true}) res:Response){
    return this.read(space,'installments',id,query,req,res);
  }
  @Get('installments/:id/payments')
  async payments(@Param('space') space:string,@Param('id') id:string,@Query() query:Record<string,unknown>,@Req() req:Request,@Res({passthrough:true}) res:Response){
    return this.read(space,'payments',id,query,req,res);
  }
  @Post('commitments')
  @HttpCode(200)
  async create(@Param('space') space:string,@Body() body:unknown,@Req() req:Request,@Res({passthrough:true}) res:Response){
    res.setHeader('Cache-Control','no-store');const token=await this.token(req,res);
    if(!validCreate(body)||Object.keys(body).some(k=>!['id','cuenta_id','nombre','moneda','importe','categoria','primer_vencimiento','total_cuotas'].includes(k)))throw new BadRequestException('Compromiso invalido');
    return this.forward(token,space,'commitments',undefined,0,{...body,id:body.id.toLowerCase(),cuenta_id:body.cuenta_id.toLowerCase(),nombre:body.nombre.trim()});
  }
  @Post('installments/:id/payments')
  @HttpCode(200)
  async pay(@Param('space') space:string,@Param('id') id:string,@Body() body:unknown,@Req() req:Request,@Res({passthrough:true}) res:Response){
    res.setHeader('Cache-Control','no-store');const token=await this.token(req,res);
    if(!validId(id)||!validPay(body)||Object.keys(body).some(k=>!['id','cuenta_id','fecha','importe'].includes(k)))throw new BadRequestException('Pago invalido');
    return this.forward(token,space,'payments',id.toLowerCase(),0,{...body,id:body.id.toLowerCase(),cuenta_id:body.cuenta_id.toLowerCase()});
  }
  private async read(space:string,kind:'commitments'|'installments'|'payments',id:string|undefined,query:Record<string,unknown>,req:Request,res:Response){
    res.setHeader('Cache-Control','no-store');const token=await this.token(req,res);
    if((id!==undefined&&!validId(id))||Object.keys(query).some(k=>k!=='offset')||
      (query.offset!==undefined&&(typeof query.offset!=='string'||!/^\d{1,6}$/.test(query.offset)||Number(query.offset)>100000)))throw new BadRequestException('Pagina invalida');
    return this.forward(token,space,kind,id?.toLowerCase(),Number(query.offset??0));
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




  private async forward(token:string,rawSpace:string,kind:'commitments'|'installments'|'payments'|'monthly'|'detail'|'pause',id:string|undefined,offset=0,body?:Create|Pay|{pausado:boolean;version:number},month?:string){
    if(!UUID.test(rawSpace))throw new BadRequestException('Espacio invalido');const space=rawSpace.toLowerCase();
    try{
      const base=new URL(process.env.API_BASE_URL??'http://127.0.0.1:8000'),local=['localhost','127.0.0.1','[::1]','api'].includes(base.hostname);
      if(base.username||base.password||base.search||base.hash||base.pathname!=='/'||(base.protocol!=='https:'&&!(base.protocol==='http:'&&local)))throw new Error();
      const rawTimeout=process.env.API_TIMEOUT_MS??'5000',timeout=Number(rawTimeout);
      if(!/^\d+$/.test(rawTimeout)||!Number.isSafeInteger(timeout)||timeout<1||timeout>2147483647)throw new Error();
      const suffix=(kind==='detail'||kind==='pause')?`commitments/${id}`:kind==='monthly'?'installments':kind==='commitments'?'commitments':kind==='installments'?`commitments/${id}/installments`:`installments/${id}/payments`;
      const result=await fetch(new URL(`/spaces/${space}/${suffix}?offset=${offset}${kind==='monthly'?'&month='+month:''}`,base),{method:kind==='pause'?'PATCH':body?'POST':'GET',redirect:'error',signal:AbortSignal.timeout(timeout),
        headers:{Accept:'application/json',Authorization:`Bearer ${token}`,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});
      if([400,401,403,404,409,422,503].includes(result.status))throw new HttpException('No se pudo completar la operacion',result.status);
      if(!result.ok)throw new Error();const data=await boundedJson(result,262144);
      if(kind==='pause'){
        const row=commitment(data,space),input=body as {pausado:boolean;version:number};
        if(row.id!==id||row.pausado!==input.pausado||row.total_cuotas!==null||![input.version,input.version+1].includes(row.version))throw new Error();
        return row;
      }
      if(kind==='detail'){const row=commitment(data,space);if(row.id!==id)throw new Error();return row;}
      if(kind==='monthly')return monthlyPage(data,space,month!,offset);
      if(body){
        if(kind==='commitments'){
          const row=commitment(data,space),input=body as Create;
          if(['id','cuenta_id','nombre','moneda','primer_vencimiento','total_cuotas'].some(k=>row[k as keyof Commitment]!==input[k as keyof Create])||
            cents(row.importe)!==cents(input.importe)||(row.categoria??null)!==(input.categoria??null))throw new Error();
          return row;
        }
        const row=payment(data,space,id!),input=body as Pay;
        if(row.id!==input.id||row.cuenta_id!==input.cuenta_id||row.fecha!==input.fecha||cents(row.importe)!==cents(input.importe))throw new Error();
        return row;
      }
      const page=data as {items:unknown[];next_offset:number|null};
      if(!page||!Array.isArray(page.items)||page.items.length>100||!(page.next_offset===null||page.next_offset===offset+100))throw new Error();
      return {items:page.items.map(row=>kind==='commitments'?commitment(row,space):kind==='installments'?installment(row,space,id!):payment(row,space,id!)),next_offset:page.next_offset};
    }catch(error){if(error instanceof HttpException)throw error;throw new BadGatewayException('No se pudo consultar FastAPI');}
  }
}
