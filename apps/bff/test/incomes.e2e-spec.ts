import { Test } from '@nestjs/testing';
import { type INestApplication } from '@nestjs/common';
import request from 'supertest';
import { randomUUID } from 'node:crypto';
import { AppModule } from '../src/app.module.js';
import { AuthService } from '../src/auth.service.js';
describe('Ingresos y saldos HTTP',()=>{
  let app:INestApplication;let remote:ReturnType<typeof vi.fn>;
  const space=randomUUID(),account=randomUUID(),path=`/api/spaces/${space}/accounts/${account}/incomes`;
  const payload={id:randomUUID(),fecha:'2026-11-16',descripcion:'Sueldo',moneda:'ARS',importe:'100.10'};
  const row={...payload,espacio_id:space,cuenta_id:account};
  const summary={totales:['ARS','USD','EUR'].map(moneda=>({moneda,ingresos:'100.10',gastos:'200.00',saldo:'-99.90'}))};
  beforeEach(async()=>{
    const module=await Test.createTestingModule({imports:[AppModule]}).overrideProvider(AuthService).useValue({verifyIdentity:vi.fn().mockResolvedValue(randomUUID())}).compile();
    app=module.createNestApplication();await app.init();
    vi.stubEnv('API_BASE_URL','https://api.example');
    remote=vi.fn().mockImplementation(async()=>new Response(JSON.stringify(row)));vi.stubGlobal('fetch',remote);
  });
  afterEach(async()=>{await app.close();vi.unstubAllEnvs();vi.unstubAllGlobals();});
  it('exige token, conserva dinero como texto y no cachea',async()=>{
    await request(app.getHttpServer()).post(path).send(payload).expect(401);expect(remote).not.toHaveBeenCalled();
    await request(app.getHttpServer()).post(path).set('Authorization','Bearer token').send(payload).expect(200).expect(row).expect('Cache-Control','no-store');
    expect(JSON.parse(remote.mock.calls[0][1].body)).toEqual(payload);
    expect(new URL(String(remote.mock.calls[0][0])).pathname).toBe(`/spaces/${space}/accounts/${account}/incomes`);
  });
  it('rechaza importes inseguros y campos que alteran el espacio',async()=>{
    for(const body of [{...payload,importe:100.1},{...payload,importe:'0'},{...payload,importe:'1.001'},{...payload,usuario_id:randomUUID()},{...payload,categoria:'otros'}]){
      await request(app.getHttpServer()).post(path).set('Authorization','Bearer token').send(body).expect(400);
    }
    expect(remote).not.toHaveBeenCalled();
  });
  it('envía categorías de ingresos precargadas y personalizadas', async () => {
    for (const categoria of ['sueldo', randomUUID()]) {
      const categorized = { ...row, categoria };
      remote.mockResolvedValueOnce(new Response(JSON.stringify(categorized)));
      await request(app.getHttpServer()).post(path).set('Authorization', 'Bearer token')
        .send({ ...payload, categoria }).expect(200).expect(categorized);
      expect(JSON.parse(remote.mock.calls.at(-1)![1].body).categoria).toBe(categoria);
    }
  });
  it('lista por cuenta o todas, valida pertenencia y conserva errores',async()=>{
    remote.mockImplementation(async()=>new Response(JSON.stringify({items:[row],next_offset:null})));
    await request(app.getHttpServer()).get(path).set('Authorization','Bearer token').expect(200);
    await request(app.getHttpServer()).get(`/api/spaces/${space}/incomes`).set('Authorization','Bearer token').expect(200);
    await request(app.getHttpServer()).get(path+'?offset=-1').set('Authorization','Bearer token').expect(400);
    remote.mockImplementation(async()=>new Response(JSON.stringify({...row,cuenta_id:randomUUID()})));
    await request(app.getHttpServer()).post(path).set('Authorization','Bearer token').send(payload).expect(502);
    for(const status of [403,404,409,422,503]){
      remote.mockImplementation(async()=>new Response('{}',{status}));
      await request(app.getHttpServer()).post(path).set('Authorization','Bearer token').send(payload).expect(status);
    }
  });
  it('admite saldo negativo y rechaza totales incoherentes o monedas duplicadas',async()=>{
    const url=`/api/spaces/${space}/account-balance?account=${account}`;
    remote.mockImplementation(async()=>new Response(JSON.stringify(summary)));
    await request(app.getHttpServer()).get(url).set('Authorization','Bearer token').expect(200).expect(summary);
    expect(new URL(String(remote.mock.calls[0][0])).searchParams.get('account')).toBe(account);
    for(const totales of [[summary.totales[0],summary.totales[0],summary.totales[2]],summary.totales.map(row=>({...row,saldo:'1.00'}))]){
      remote.mockImplementation(async()=>new Response(JSON.stringify({totales})));
      await request(app.getHttpServer()).get(url).set('Authorization','Bearer token').expect(502);
    }
  });
});
