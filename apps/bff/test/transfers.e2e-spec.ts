import { Test } from '@nestjs/testing';
import { type INestApplication } from '@nestjs/common';
import request from 'supertest';
import { randomUUID } from 'node:crypto';
import { AppModule } from '../src/app.module.js';
import { AuthService } from '../src/auth.service.js';
describe('Transferencias HTTP',()=>{
  let app:INestApplication;let remote:ReturnType<typeof vi.fn>;
  const space=randomUUID(),origin=randomUUID(),destination=randomUUID(),path=`/api/spaces/${space}/transfers`;
  const payload={id:randomUUID(),origen_id:origin,destino_id:destination,fecha:'2026-11-17',descripcion:'Ahorro',moneda:'ARS',importe:'100.10'};
  const row={...payload,espacio_id:space};
  beforeEach(async()=>{
    const module=await Test.createTestingModule({imports:[AppModule]}).overrideProvider(AuthService).useValue({verifyIdentity:vi.fn().mockResolvedValue(randomUUID())}).compile();
    app=module.createNestApplication();await app.init();vi.stubEnv('API_BASE_URL','https://api.example');
    remote=vi.fn().mockImplementation(async()=>new Response(JSON.stringify(row)));vi.stubGlobal('fetch',remote);
  });
  afterEach(async()=>{await app.close();vi.unstubAllEnvs();vi.unstubAllGlobals();});
  it('exige token y conserva cuentas, UUID y decimal sin cache',async()=>{
    await request(app.getHttpServer()).post(path).send(payload).expect(401);expect(remote).not.toHaveBeenCalled();
    await request(app.getHttpServer()).post(path).set('Authorization','Bearer token').send(payload).expect(200).expect(row).expect('Cache-Control','no-store');
    expect(JSON.parse(remote.mock.calls[0][1].body)).toEqual(payload);
    expect(new URL(String(remote.mock.calls[0][0])).pathname).toBe(`/spaces/${space}/transfers`);
  });
  it('rechaza la misma cuenta, conversiones y entradas inseguras',async()=>{
    for(const bad of [{...payload,destino_id:origin.toUpperCase()},{...payload,importe:100.1},{...payload,importe:'1.001'},{...payload,moneda_destino:'USD'},{...payload,usuario_id:randomUUID()}]){
      await request(app.getHttpServer()).post(path).set('Authorization','Bearer token').send(bad).expect(400);
    }
    expect(remote).not.toHaveBeenCalled();
  });
  it('filtra cualquiera de los dos lados y rechaza filas ajenas o datos alterados',async()=>{
    remote.mockImplementation(async()=>new Response(JSON.stringify({items:[row],next_offset:null})));
    await request(app.getHttpServer()).get(path+'?account='+destination).set('Authorization','Bearer token').expect(200);
    expect(new URL(String(remote.mock.calls[0][0])).searchParams.get('account')).toBe(destination);
    await request(app.getHttpServer()).get(path+'?offset=-1').set('Authorization','Bearer token').expect(400);
    remote.mockImplementation(async()=>new Response(JSON.stringify({items:[row],next_offset:null})));
    await request(app.getHttpServer()).get(path+'?account='+randomUUID()).set('Authorization','Bearer token').expect(502);
    for(const bad of [{...row,importe:'100.11'},{...row,origen_id:randomUUID()},{...row,espacio_id:randomUUID()}]){
      remote.mockImplementation(async()=>new Response(JSON.stringify(bad)));
      await request(app.getHttpServer()).post(path).set('Authorization','Bearer token').send(payload).expect(502);
    }
  });
  it('conserva permisos y conflictos del servidor',async()=>{
    for(const status of [403,404,409,422,503]){
      remote.mockImplementation(async()=>new Response('{}',{status}));
      await request(app.getHttpServer()).post(path).set('Authorization','Bearer token').send(payload).expect(status);
    }
  });
  it('valida saldos con transferencias y conserva ingresos y gastos separados',async()=>{
    const url=`/api/spaces/${space}/account-balance?account=${origin}`;
    const summary={totales:['ARS','USD','EUR'].map(moneda=>({moneda,ingresos:'100.00',gastos:'20.00',transferencias_entrada:'10.00',transferencias_salida:'30.00',saldo:'60.00'}))};
    remote.mockImplementation(async()=>new Response(JSON.stringify(summary)));
    await request(app.getHttpServer()).get(url).set('Authorization','Bearer token').expect(200).expect(summary);
    for(const changes of [{saldo:'80.00'},{transferencias_salida:'-1.00'},{transferencias_entrada:10}]){
      remote.mockImplementation(async()=>new Response(JSON.stringify({totales:summary.totales.map(row=>({...row,...changes}))})));
      await request(app.getHttpServer()).get(url).set('Authorization','Bearer token').expect(502);
    }
  });
});
