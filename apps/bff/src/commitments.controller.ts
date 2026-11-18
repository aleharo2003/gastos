import { BadGatewayException,BadRequestException,Body,Controller,Get,HttpCode,HttpException,Param,Patch,Post,Query,Req,Res,UnauthorizedException } from '@nestjs/common';
import type { Request,Response } from 'express';
import { AuthService } from './auth.service.js';
import { validateBalance } from './incomes.controller.js';
import { validLimits } from './planning.controller.js';
import { boundedJson } from './token-verifier.js';
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const validId=(v:unknown):v is string=>typeof v==='string'&&UUID.test(v)&&!/^0{8}-0{4}-0{4}-0{4}-0{12}$/.test(v);
const date=(v:unknown):v is string=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v);
const currencies=['ARS','USD','EUR'];
const categories=['alimentos','transporte','vivienda','servicios','salud','educacion','ocio','impuestos','auto','bancario','ropa','otros'];
const amount=(v:unknown):v is string=>typeof v==='string'&&/^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?$/.test(v)&&/[1-9]/.test(v);
const sum=(v:unknown):v is string=>typeof v==='string'&&v.length<=40&&/^(?:0|[1-9][0-9]*)\.[0-9]{2}$/.test(v);
const cents=(v:string)=>{const [whole,fraction='']=v.split('.');return BigInt(whole)*100n+BigInt(fraction.padEnd(2,'0'));};
type Create={variable?:boolean;id:string;cuenta_id:string;nombre:string;moneda:string;importe:string;categoria?:string|null;primer_vencimiento:string;total_cuotas:number|null};
type Confirm={items:{id:string;importe:string;version:number}[]};
type Pay={id:string;cuenta_id:string;fecha:string;importe:string};
type Commitment=Create & {variable:boolean;pausado:boolean;version:number;espacio_id:string;cuotas_pagadas:number;cuotas_no_aplican:number;total:string;pagado:string;pendiente:string;proximo_vencimiento:string|null};
type Installment={estimado:boolean;version:number;id:string;espacio_id:string;compromiso_id:string;numero:number;vencimiento:string;importe:string;pagado:string;pendiente:string;estado:string;vencida:boolean};
type Payment=Pay & {espacio_id:string;cuota_id:string;moneda:string};
function validCreate(v:unknown):v is Create{
  const r=v as Create;
  return !!r&&validId(r.id)&&validId(r.cuenta_id)&&typeof r.nombre==='string'&&[...r.nombre.trim()].length>=1&&[...r.nombre.trim()].length<=160&&
    !/[\x00-\x1f\x7f]/.test(r.nombre)&&currencies.includes(r.moneda)&&amount(r.importe)&&date(r.primer_vencimiento)&&
    (r.total_cuotas===null||(Number.isInteger(r.total_cuotas)&&r.total_cuotas>=1&&r.total_cuotas<=600))&&(r.categoria==null||categories.includes(r.categoria))&&
    (r.variable===undefined||typeof r.variable==='boolean')&&(!r.variable||r.total_cuotas===null);
}
function validPay(v:unknown):v is Pay{
  const r=v as Pay;return !!r&&validId(r.id)&&validId(r.cuenta_id)&&date(r.fecha)&&amount(r.importe);
}
function commitment(v:unknown,space:string):Commitment{
  const r=v as Commitment;
  if(!validCreate(r)||r.espacio_id!==space||!Number.isInteger(r.cuotas_pagadas)||r.cuotas_pagadas<0||(r.total_cuotas!==null&&r.cuotas_pagadas+r.cuotas_no_aplican>r.total_cuotas)||!Number.isSafeInteger(r.cuotas_no_aplican)||r.cuotas_no_aplican<0||typeof r.variable!=='boolean'||typeof r.pausado!=='boolean'||!Number.isSafeInteger(r.version)||r.version<1||
    !sum(r.total)||!sum(r.pagado)||!sum(r.pendiente)||(r.total_cuotas!==null&&cents(r.total)!==cents(r.importe)*BigInt(r.total_cuotas-r.cuotas_no_aplican))||
    cents(r.pagado)+cents(r.pendiente)!==cents(r.total)||!(r.proximo_vencimiento===null||date(r.proximo_vencimiento))||
    (cents(r.pendiente)===0n)!==(r.proximo_vencimiento===null)||(!r.variable&&BigInt(r.cuotas_pagadas)*cents(r.importe)>cents(r.pagado)))throw new Error();
  return {variable:r.variable,id:r.id,espacio_id:space,cuenta_id:r.cuenta_id,nombre:r.nombre,moneda:r.moneda,importe:r.importe,categoria:r.categoria??null,
    primer_vencimiento:r.primer_vencimiento,total_cuotas:r.total_cuotas,pausado:r.pausado,version:r.version,cuotas_no_aplican:r.cuotas_no_aplican,cuotas_pagadas:r.cuotas_pagadas,total:r.total,pagado:r.pagado,pendiente:r.pendiente,proximo_vencimiento:r.proximo_vencimiento};
}
function installment(v:unknown,space:string,id:string):Installment{
  const r=v as Installment;
  if(!r||!validId(r.id)||r.espacio_id!==space||r.compromiso_id!==id||!Number.isInteger(r.numero)||r.numero<1||r.numero>119988||
    !date(r.vencimiento)||!amount(r.importe)||!sum(r.pagado)||!sum(r.pendiente)||(r.estado==='no_aplica'?(r.pagado!=='0.00'||r.pendiente!=='0.00'||r.estimado||r.vencida):cents(r.pagado)+cents(r.pendiente)!==cents(r.importe))||
    typeof r.estimado!=='boolean'||!Number.isInteger(r.version)||r.version<1||
    (r.estimado&&r.pagado!=='0.00')||(r.estado!=='no_aplica'&&r.estado!==(r.estimado?'borrador':cents(r.pendiente)===0n?'pagada':cents(r.pagado)>0n?'parcial':'pendiente'))||typeof r.vencida!=='boolean'||(r.estado==='pagada'&&r.vencida))throw new Error();
  return {estimado:r.estimado,version:r.version,id:r.id,espacio_id:space,compromiso_id:id,numero:r.numero,vencimiento:r.vencimiento,importe:r.importe,pagado:r.pagado,pendiente:r.pendiente,estado:r.estado,vencida:r.vencida};
}
function payment(v:unknown,space:string,id:string):Payment{
  const r=v as Payment;if(!validPay(r)||r.espacio_id!==space||r.cuota_id!==id||!currencies.includes(r.moneda))throw new Error();
  return {id:r.id,espacio_id:space,cuota_id:id,cuenta_id:r.cuenta_id,fecha:r.fecha,moneda:r.moneda,importe:r.importe};
}
type MonthlyItem=Installment & {nombre:string;moneda:string;cuenta_id:string};
type MonthlyTotal={no_aplican:number;borradores:number;estimado:string;moneda:string;cuotas:number;cuotas_pagadas:number;total:string;pagado:string;pendiente:string;vencido:string};
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
      !Number.isSafeInteger(t.no_aplican)||t.no_aplican<0||t.no_aplican+t.cuotas_pagadas+t.borradores>t.cuotas||!Number.isInteger(t.borradores)||t.borradores<0||t.borradores>t.cuotas||!sum(t.estimado)||
      cents(t.estimado)>cents(t.pendiente)||!sum(t.total)||!sum(t.pagado)||!sum(t.pendiente)||!sum(t.vencido)||
      cents(t.total)!==cents(t.pagado)+cents(t.pendiente)||cents(t.vencido)>cents(t.pendiente))throw new Error();
    seen.add(t.moneda);return {no_aplican:t.no_aplican,borradores:t.borradores,estimado:t.estimado,moneda:t.moneda,cuotas:t.cuotas,cuotas_pagadas:t.cuotas_pagadas,total:t.total,pagado:t.pagado,pendiente:t.pendiente,vencido:t.vencido};
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
const dueGroups = ['hoy','semana','vencidas'] as const;
type DueGroupKey = typeof dueGroups[number];
type DueTotal = { moneda:string; pendiente:string };
type DueItem = DueTotal & { id:string; nombre:string; numero:number; vencimiento:string; estimado:boolean };
type DueGroup = { cantidad:number; totales:DueTotal[]; items:DueItem[] };
type DueOverview = {
  fecha:string;
  fin_semana:string;
  grupos:Record<DueGroupKey,DueGroup>;
  resumen_mes:(DueTotal & { pagado:string })[];
  saldos:unknown;
  presupuesto:{limites:unknown;gastos:{moneda:string;dia:string;mes:string;semana:string}[]};
};

function dueTotals<T extends DueTotal>(value:T[]):T[]{
  if(!Array.isArray(value)||value.length>3||new Set(value.map(row=>row?.moneda)).size!==value.length)throw new Error();
  for(const row of value){
    if(!row||!currencies.includes(row.moneda)||!sum(row.pendiente))throw new Error();
  }
  return value;
}

function dueOverview(value:unknown){
  const page=value as DueOverview;
  if(!page||!date(page.fecha)||!date(page.fin_semana)||page.fin_semana<page.fecha||!page.grupos)throw new Error();
  const groups=dueGroups.map(key=>{
    const group=page.grupos[key];
    if(!group||!Number.isSafeInteger(group.cantidad)||group.cantidad<0||!Array.isArray(group.items)||
       group.items.length!==Math.min(group.cantidad,20))throw new Error();
    const totals=dueTotals(group.totales).map(({moneda,pendiente})=>{
      if(cents(pendiente)<=0n)throw new Error();
      return {moneda,pendiente};
    });
    if((group.cantidad===0)!==(totals.length===0))throw new Error();
    const seen=new Set<string>();
    const items=group.items.map(row=>{
      if(!row||!validId(row.id)||seen.has(row.id)||typeof row.nombre!=='string'||!row.nombre.trim()||
         [...row.nombre].length>160||!Number.isInteger(row.numero)||row.numero<1||row.numero>119988||
         !date(row.vencimiento)||typeof row.estimado!=='boolean'||!sum(row.pendiente)||cents(row.pendiente)<=0n||
         !totals.some(total=>total.moneda===row.moneda)||
         (key==='hoy'&&row.vencimiento!==page.fecha)||
         (key==='vencidas'&&row.vencimiento>=page.fecha)||
         (key==='semana'&&(row.vencimiento<=page.fecha||row.vencimiento>page.fin_semana)))throw new Error();
      seen.add(row.id);
      const {id,nombre,numero,vencimiento,moneda,pendiente,estimado}=row;
      return {id,nombre,numero,vencimiento,moneda,pendiente,estimado};
    });
    return [key,{cantidad:group.cantidad,totales:totals,items}] as const;
  });
  const month=dueTotals(page.resumen_mes).map(({moneda,pendiente,pagado})=>{
    if(!sum(pagado))throw new Error();
    return {moneda,pendiente,pagado};
  });
  const saldos=validateBalance(page.saldos).totales.map(({moneda,saldo})=>({moneda,saldo}));
  const budget=page.presupuesto;
  if(!budget||!validLimits(budget.limites)||!Array.isArray(budget.gastos)||budget.gastos.length>3)throw new Error();
  const currenciesSeen=new Set<string>();
  const gastos=budget.gastos.map(row=>{
    if(!row||!currencies.includes(row.moneda)||currenciesSeen.has(row.moneda)||
       !sum(row.dia)||!sum(row.mes)||!sum(row.semana)||cents(row.dia)>cents(row.semana))throw new Error();
    currenciesSeen.add(row.moneda);
    return {moneda:row.moneda,dia:row.dia,mes:row.mes,semana:row.semana};
  });
  return {fecha:page.fecha,fin_semana:page.fin_semana,grupos:Object.fromEntries(groups),resumen_mes:month,
    saldos,presupuesto:{limites:budget.limites,gastos}};

}

type IndexValue = { indice: string; periodo: string; variacion: string };

function validIndexValue(value: unknown): value is IndexValue {
  const row = value as IndexValue;
  return !!row && typeof row.indice === 'string' && row.indice === row.indice.trim() &&
    [...row.indice].length >= 1 && [...row.indice].length <= 80 && !/[\x00-\x1f\x7f]/.test(row.indice) &&
    typeof row.periodo === 'string' && /^(?!0000)[0-9]{4}-(0[1-9]|1[0-2])$/.test(row.periodo) &&
    typeof row.variacion === 'string' && /^-?[0-9]{1,6}(\.[0-9]{1,4})?$/.test(row.variacion) &&
    Number(row.variacion) > -100;
}

@Controller('api/spaces/:space')
export class CommitmentsController{
  constructor(private readonly auth:AuthService){}
  @Get('index-values')
  async listIndexValues(
    @Param('space') space: string, @Query() query: Record<string, unknown>,
    @Req() req: Request, @Res({passthrough: true}) res: Response,
  ) {
    res.setHeader('Cache-Control', 'no-store');
    const token = await this.token(req, res);
    if (Object.keys(query).some(key => key !== 'offset') ||
        (query.offset !== undefined && (typeof query.offset !== 'string' ||
          !/^\d{1,6}$/.test(query.offset) || Number(query.offset) > 100000))) {
      throw new BadRequestException('Pagina invalida');
    }
    return this.forward(token, space, 'index-values', undefined, Number(query.offset ?? 0));
  }

  @Post('index-values')
  @HttpCode(200)
  async saveIndexValue(
    @Param('space') space: string, @Body() body: unknown,
    @Req() req: Request, @Res({passthrough: true}) res: Response,
  ) {
    res.setHeader('Cache-Control', 'no-store');
    const token = await this.token(req, res);
    if (!validIndexValue(body) || Object.keys(body).length !== 3) {
      throw new BadRequestException('Variacion invalida');
    }
    return this.forward(token, space, 'index-values', undefined, 0, body);
  }

  @Post('installments/:id/skip')
  @HttpCode(200)
  async skip(@Param('space') space:string,@Param('id') id:string,@Body() body:unknown,
             @Req() req:Request,@Res({passthrough:true}) res:Response){
    res.setHeader('Cache-Control','no-store');
    const token=await this.token(req,res);
    const value=body as {version:number};
    if(!validId(id)||!value||Object.keys(value).length!==1||
       !Number.isInteger(value.version)||value.version<1||value.version>2147483646){
      throw new BadRequestException('Version invalida');
    }
    return this.forward(token,space,'skip',id.toLowerCase(),0,{version:value.version});
  }

  @Get('due-overview')
  async overview(@Param('space') space:string,@Query() query:Record<string,unknown>,
                 @Req() req:Request,@Res({passthrough:true}) res:Response){
    res.setHeader('Cache-Control','no-store');
    const token=await this.token(req,res);
    if(Object.keys(query).length)throw new BadRequestException('Consulta invalida');
    return this.forward(token,space,'overview',undefined);
  }

  @Get('installment-drafts')
  async drafts(@Param('space') space:string,@Query() query:Record<string,unknown>,@Req() req:Request,@Res({passthrough:true}) res:Response){
    res.setHeader('Cache-Control','no-store');const token=await this.token(req,res);
    if(Object.keys(query).some(k=>k!=='offset')||(query.offset!==undefined&&
      (typeof query.offset!=='string'||!/^\d{1,6}$/.test(query.offset)||Number(query.offset)>100000)))throw new BadRequestException('Pagina invalida');
    return this.forward(token,space,'drafts',undefined,Number(query.offset??0));
  }
  @Post('installment-confirmations')
  @HttpCode(200)
  async confirm(@Param('space') space:string,@Body() body:unknown,@Req() req:Request,@Res({passthrough:true}) res:Response){
    res.setHeader('Cache-Control','no-store');const token=await this.token(req,res);
    const value=body as Confirm;
    if(!value||Object.keys(value).some(k=>k!=='items')||!Array.isArray(value.items)||value.items.length<1||value.items.length>100||
      value.items.some(t=>!t||!validId(t.id)||!amount(t.importe)||!Number.isInteger(t.version)||t.version<1||t.version>2147483646||
        Object.keys(t).some(k=>!['id','importe','version'].includes(k)))||
      new Set(value.items.map(t=>t.id.toLowerCase())).size!==value.items.length)throw new BadRequestException('Confirmacion invalida');
    return this.forward(token,space,'confirm',undefined,0,{items:value.items.map(t=>({...t,id:t.id.toLowerCase()}))});
  }
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
    if(!validCreate(body)||Object.keys(body).some(k=>!['id','cuenta_id','nombre','moneda','importe','categoria','primer_vencimiento','total_cuotas','variable'].includes(k)))throw new BadRequestException('Compromiso invalido');
    return this.forward(token,space,'commitments',undefined,0,{...body,id:body.id.toLowerCase(),cuenta_id:body.cuenta_id.toLowerCase(),nombre:body.nombre.trim()});
  }
  @Post('installments/:id/payments')
  @HttpCode(200)
  async pay(@Param('space') space:string,@Param('id') id:string,@Body() body:unknown,@Req() req:Request,@Res({passthrough:true}) res:Response){
    res.setHeader('Cache-Control','no-store');const token=await this.token(req,res);
    if(!validId(id)||!validPay(body)||Object.keys(body).some(k=>!['id','cuenta_id','fecha','importe'].includes(k)))throw new BadRequestException('Pago invalido');
    return this.forward(token,space,'payments',id.toLowerCase(),0,{...body,id:body.id.toLowerCase(),cuenta_id:body.cuenta_id.toLowerCase()});
  }
  private async read(space:string,kind:'index-values'|'commitments'|'installments'|'payments',id:string|undefined,query:Record<string,unknown>,req:Request,res:Response){
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




  private async forward(token:string,rawSpace:string,kind:'commitments'|'installments'|'payments'|'monthly'|'detail'|'pause'|'drafts'|'confirm'|'skip'|'overview',id:string|undefined,offset=0,body?:IndexValue|Create|Pay|Confirm|{version:number}|{pausado:boolean;version:number},month?:string){
    if(!UUID.test(rawSpace))throw new BadRequestException('Espacio invalido');const space=rawSpace.toLowerCase();
    try{
      const base=new URL(process.env.API_BASE_URL??'http://127.0.0.1:8000'),local=['localhost','127.0.0.1','[::1]','api'].includes(base.hostname);
      if(base.username||base.password||base.search||base.hash||base.pathname!=='/'||(base.protocol!=='https:'&&!(base.protocol==='http:'&&local)))throw new Error();
      const rawTimeout=process.env.API_TIMEOUT_MS??'5000',timeout=Number(rawTimeout);
      if(!/^\d+$/.test(rawTimeout)||!Number.isSafeInteger(timeout)||timeout<1||timeout>2147483647)throw new Error();
      const suffix=kind==='index-values'?'index-values':kind==='overview'?'due-overview':kind==='skip'?`installments/${id}/skip`:kind==='drafts'?'installment-drafts':kind==='confirm'?'installment-confirmations':(kind==='detail'||kind==='pause')?`commitments/${id}`:kind==='monthly'?'installments':kind==='commitments'?'commitments':kind==='installments'?`commitments/${id}/installments`:`installments/${id}/payments`;
      const result=await fetch(new URL(`/spaces/${space}/${suffix}?offset=${offset}${kind==='monthly'?'&month='+month:''}`,base),{method:kind==='pause'?'PATCH':body?'POST':'GET',redirect:'error',signal:AbortSignal.timeout(timeout),
        headers:{Accept:'application/json',Authorization:`Bearer ${token}`,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});
      if([400,401,403,404,409,422,503].includes(result.status))throw new HttpException('No se pudo completar la operacion',result.status);
      if(!result.ok)throw new Error();const data=await boundedJson(result,262144);
      if (kind === 'index-values') {
        if (body) {
          const input = body as IndexValue;
          if (!validIndexValue(data) || data.indice !== input.indice || data.periodo !== input.periodo ||
              Number(data.variacion) !== Number(input.variacion)) throw new Error();
          const { indice, periodo, variacion } = data;
          return { indice, periodo, variacion };
        }
        const page = data as { items: unknown[]; next_offset: number | null };
        if (!page || !Array.isArray(page.items) || page.items.length > 100 ||
            !(page.next_offset === null || (page.items.length === 100 && page.next_offset === offset + 100))) {
          throw new Error();
        }
        const items = page.items.map(value => {
          if (!validIndexValue(value)) throw new Error();
          const { indice, periodo, variacion } = value;
          return { indice, periodo, variacion };
        });
        return { items, next_offset: page.next_offset };
      }
      if(kind==='skip'){
        const row=data as {id:string;estado:string;version:number};
        if(!row||row.id!==id||row.estado!=='no_aplica'||row.version!==(body as {version:number}).version+1)throw new Error();
        return {id:row.id,estado:row.estado,version:row.version};
      }
      if(kind==='confirm'){
        const ids=(data as {confirmadas:string[]})?.confirmadas,input=body as Confirm;
        if(!Array.isArray(ids)||ids.length!==input.items.length||ids.some((id,index)=>id!==input.items[index].id))throw new Error();
        return {confirmadas:ids};
      }
      if(kind==='drafts'){
        const page=data as {borradores:number;items:unknown[];next_offset:number|null};
        if(!page||!Number.isSafeInteger(page.borradores)||page.borradores<0||!Array.isArray(page.items)||page.items.length>100||
          !(page.next_offset===null||page.next_offset===offset+100))throw new Error();
        const items=page.items.map(value=>{
          const t=value as Installment & {nombre:string;moneda:string;cuenta_id:string};
          if(!t||typeof t.nombre!=='string'||!t.nombre.trim()||[...t.nombre].length>160||!currencies.includes(t.moneda)||
            !validId(t.cuenta_id)||!validId(t.compromiso_id)||!t.estimado)throw new Error();
          return {...installment(t,space,t.compromiso_id),nombre:t.nombre,moneda:t.moneda,cuenta_id:t.cuenta_id};
        });
        if(page.borradores<items.length||new Set(items.map(t=>t.id)).size!==items.length)throw new Error();
        return {borradores:page.borradores,items,next_offset:page.next_offset};
      }
      if(kind==='pause'){
        const row=commitment(data,space),input=body as {pausado:boolean;version:number};
        if(row.id!==id||row.pausado!==input.pausado||row.total_cuotas!==null||![input.version,input.version+1].includes(row.version))throw new Error();
        return row;
      }
      if(kind==='detail'){const row=commitment(data,space);if(row.id!==id)throw new Error();return row;}
      if(kind==='overview')return dueOverview(data);
      if(kind==='monthly')return monthlyPage(data,space,month!,offset);
      if(body){
        if(kind==='commitments'){
          const row=commitment(data,space),input=body as Create;
          if(['id','cuenta_id','nombre','moneda','primer_vencimiento','total_cuotas'].some(k=>row[k as keyof Commitment]!==input[k as keyof Create])||
            row.variable!==(input.variable??false)||cents(row.importe)!==cents(input.importe)||(row.categoria??null)!==(input.categoria??null))throw new Error();
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
