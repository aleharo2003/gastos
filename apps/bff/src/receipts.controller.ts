import { BadGatewayException, BadRequestException, Controller, Get, HttpException, Param, Post, Req, Res, UnauthorizedException } from '@nestjs/common';
import type { Request, Response } from 'express';
import { AuthService } from './auth.service.js';
import { boundedJson } from './token-verifier.js';

const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MAX=5*1024*1024;

@Controller('api/spaces/:space/accounts/:account/expenses/:expense/receipts')
export class ReceiptsController {
  constructor(private readonly auth:AuthService){}
  private async prepare(request:Request,response:Response,params:Record<string,string>){
    response.setHeader('Cache-Control','no-store');
    const count=request.rawHeaders.filter((v,i)=>i%2===0&&v.toLowerCase()==='authorization').length;
    const parts=request.headers.authorization?.trim().split(/\s+/)??[];
    if(count!==1||parts.length!==2||parts[0].toLowerCase()!=='bearer') throw new UnauthorizedException();
    await this.auth.verifyIdentity(parts[1]);
    if(Object.values(params).some(v=>!UUID.test(v))) throw new BadRequestException();
    return parts[1];
  }
  private path(p:Record<string,string>){return `/spaces/${p.space}/accounts/${p.account}/expenses/${p.expense}/receipts`;}
  private async call(token:string,path:string,body?:Buffer,name?:string){
    try{
      const base=new URL(process.env.API_BASE_URL??'http://127.0.0.1:8000');
      const local=['localhost','127.0.0.1','[::1]','api'].includes(base.hostname);
      if(base.username||base.password||base.search||base.hash||base.pathname!=='/'||
        (base.protocol!=='https:'&&!(base.protocol==='http:'&&local)))throw new Error();
      const raw=process.env.API_TIMEOUT_MS??'120000',timeout=Number(raw);
      if(!/^\d+$/.test(raw)||!Number.isSafeInteger(timeout)||timeout<1||timeout>2147483647)throw new Error();
      const result=await fetch(new URL(path,base),{method:body?'POST':'GET',redirect:'error',signal:AbortSignal.timeout(timeout),
        headers:{Authorization:`Bearer ${token}`,...(body?{'Content-Type':'application/octet-stream','X-Receipt-Name':name!}:{})},
        ...(body?{body:new Uint8Array(body)}:{})});
      if([400,401,403,404,409,413,415,422,503].includes(result.status))throw new HttpException('No se pudo completar la operación del comprobante',result.status);
      if(!result.ok)throw new Error();
      return result;
    }catch(e){if(e instanceof HttpException)throw e;throw new BadGatewayException('No se pudo consultar el comprobante');}
  }
  @Get()
  async list(@Param() p:Record<string,string>,@Req() req:Request,@Res({passthrough:true}) res:Response){
    const token=await this.prepare(req,res,p);
    try{return await boundedJson(await this.call(token,this.path(p)),16384);}
    catch(e){if(e instanceof HttpException)throw e;throw new BadGatewayException();}
  }
  @Post(':receipt')
  async upload(@Param() p:Record<string,string>,@Req() req:Request,@Res({passthrough:true}) res:Response){
    const token=await this.prepare(req,res,p),name=req.headers['x-receipt-name'];
    if(req.headers['content-type']!=='application/octet-stream'||typeof name!=='string'||name.length>1920)throw new BadRequestException();
    const chunks:Buffer[]=[];let size=0;
    for await(const chunk of req){const bytes=Buffer.from(chunk);size+=bytes.length;if(size>MAX)throw new HttpException('Máximo 5 MB',413);chunks.push(bytes);}
    if(!size)throw new BadRequestException('Archivo vacío');
    try{return await boundedJson(await this.call(token,this.path(p)+'/'+p.receipt,Buffer.concat(chunks),name),16384);}
    catch(e){if(e instanceof HttpException)throw e;throw new BadGatewayException();}
  }
  @Get(':receipt/file')
  async download(@Param() p:Record<string,string>,@Req() req:Request,@Res() res:Response){
    const token=await this.prepare(req,res,p),response=await this.call(token,this.path(p)+'/'+p.receipt+'/file');
    const mime=response.headers.get('content-type')?.split(';')[0];
    const extension:Record<string,string>={'image/jpeg':'jpg','image/png':'png','application/pdf':'pdf'};
    if(!mime||!extension[mime]||!response.body)throw new BadGatewayException();
    const reader=response.body.getReader(),chunks:Uint8Array[]=[];let size=0;
    try{while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>MAX)throw new Error();chunks.push(value);}}
    catch{await reader.cancel();throw new BadGatewayException();}finally{reader.releaseLock();}
    res.setHeader('Content-Type',mime);res.setHeader('X-Content-Type-Options','nosniff');
    res.setHeader('Content-Disposition',`attachment; filename="comprobante-${p.receipt.toLowerCase()}.${extension[mime]}"`);
    res.send(Buffer.concat(chunks));
  }
}
