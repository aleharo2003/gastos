import { Test } from '@nestjs/testing';
import { type INestApplication } from '@nestjs/common';
import request from 'supertest';
import { randomUUID } from 'node:crypto';
import { AppModule } from '../src/app.module.js';
import { AuthService } from '../src/auth.service.js';
describe('Presupuestos HTTP',()=>{
  let app:INestApplication;let fetchMock:ReturnType<typeof vi.fn>;
  const space=randomUUID(),path=`/api/spaces/${space}/spending-plan`;
  const value={version:0,datos:{limites:{diario:null,semanal:{moneda:'USD',importe:'200.00'}},conceptos:[]}};
  beforeEach(async()=>{
    const module=await Test.createTestingModule({imports:[AppModule]}).overrideProvider(AuthService).useValue({verifyIdentity:vi.fn().mockResolvedValue(randomUUID())}).compile();
    app=module.createNestApplication();await app.init();vi.stubEnv('API_BASE_URL','https://api.example');fetchMock=vi.fn().mockImplementation(async()=>new Response(JSON.stringify(value)));vi.stubGlobal('fetch',fetchMock);
  });
  afterEach(async()=>{await app.close();vi.unstubAllEnvs();vi.unstubAllGlobals();});
  it('solo usa el token y el espacio para consultar o guardar los avisos propios', async () => {
    const route = `/api/spaces/${space}/reminder-preferences`;
    const preferences = {
      canal:'ninguno', dias_anticipacion:5, hora_local:'18:45',
      vencimientos:true, vencidas:false, resumen_semanal:false,
    };
    fetchMock.mockImplementation(async () => new Response(JSON.stringify(preferences)));
    await request(app.getHttpServer()).get(route).expect(401);
    await request(app.getHttpServer()).post(route).set('Authorization','Bearer token')
      .send({...preferences,usuario_id:randomUUID()}).expect(400);
    expect(fetchMock).not.toHaveBeenCalled();
    await request(app.getHttpServer()).get(route).set('Authorization','Bearer token')
      .expect(200).expect(preferences).expect('Cache-Control','no-store');
    await request(app.getHttpServer()).post(route).set('Authorization','Bearer token')
      .send(preferences).expect(200).expect(preferences);
    expect(fetchMock.mock.calls[1][0].pathname).toBe(`/spaces/${space}/reminder-preferences`);
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method:'PUT', body:JSON.stringify(preferences) });
    fetchMock.mockImplementation(async () => new Response(JSON.stringify({...preferences,hora_local:'24:00'})));
    await request(app.getHttpServer()).get(route).set('Authorization','Bearer token').expect(502);
  });
  it('consulta y guarda cotizaciones manuales por fecha', async () => {
    const route = `/api/spaces/${space}/usd-reference`;
    const cotizacion = { fecha: '2026-11-12', tasa: '1720.2500' };
    fetchMock.mockImplementation(async () => new Response(JSON.stringify({ cotizacion })));
    await request(app.getHttpServer()).get(route + '?fecha=2026-11-12').set('Authorization', 'Bearer token')
      .expect(200).expect({ cotizacion }).expect('Cache-Control', 'no-store');
    expect(new URL(String(fetchMock.mock.calls[0][0])).searchParams.get('fecha')).toBe(cotizacion.fecha);
    await request(app.getHttpServer()).post(route).set('Authorization', 'Bearer token')
      .send(cotizacion).expect(200).expect({ cotizacion });
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: 'POST', body: JSON.stringify(cotizacion) });
    await request(app.getHttpServer()).post(route).set('Authorization', 'Bearer token')
      .send({ ...cotizacion, tasa: '0.00' }).expect(400);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
  it('requiere token y reenvia lectura y guardado sin cache',async()=>{
    await request(app.getHttpServer()).get(path).expect(401);expect(fetchMock).not.toHaveBeenCalled();
    await request(app.getHttpServer()).get(path).set('Authorization','Bearer token').expect(200).expect(value).expect('Cache-Control','no-store');
    await request(app.getHttpServer()).post(path).set('Authorization','Bearer token').send(value).expect(200);
    expect(new URL(String(fetchMock.mock.calls[1][0])).pathname).toBe(`/spaces/${space}/spending-plan`);
    expect(fetchMock.mock.calls[1][1].method).toBe('POST');
  });
  it('rechaza importes numericos, campos ajenos y conceptos duplicados',async()=>{
    const concept={id:randomUUID(),concepto:'Verduras',moneda:'ARS',importe:'30000.00',frecuencia:'semana'};
    for(const bad of [{...value,version:true},{...value,cuenta_id:randomUUID()},{...value,datos:{...value.datos,conceptos:[concept,concept]}},{...value,datos:{...value.datos,limites:{diario:null,semanal:{moneda:'USD',importe:200}}}}]){
      await request(app.getHttpServer()).post(path).set('Authorization','Bearer token').send(bad).expect(400);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('reenvía límites por categoría y rechaza categorías inválidas o duplicadas', async () => {
    const limit = { categoria: 'alimentos', moneda: 'ARS', importe: '30000.00' };
    const withLimits = { ...value, datos: { ...value.datos, limites_categoria: [limit] } };
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(withLimits)));
    await request(app.getHttpServer()).post(path).set('Authorization', 'Bearer token')
      .send(withLimits).expect(200).expect(withLimits);
    expect(fetchMock.mock.calls[0][1].body).toBe(JSON.stringify(withLimits));
    for (const limits of [[limit, limit], [{ ...limit, categoria: 'inventada' }], null]) {
      await request(app.getHttpServer()).post(path).set('Authorization', 'Bearer token')
        .send({ ...value, datos: { ...value.datos, limites_categoria: limits } }).expect(400);
    }
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it('reenvía el límite mensual global y valida su moneda e importe', async () => {
    const limit = { moneda: 'ARS', importe: '30000.00' };
    const withMonthly = (mensual: unknown) => ({
      ...value,
      datos: { ...value.datos, limites: { ...value.datos.limites, mensual } },
    });
    const payload = withMonthly(limit);
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(payload)));
    await request(app.getHttpServer()).post(path).set('Authorization', 'Bearer token')
      .send(payload).expect(200).expect(payload);
    expect(fetchMock.mock.calls[0][1].body).toBe(JSON.stringify(payload));
    for (const invalid of [{ ...limit, moneda: 'EUR' }, { ...limit, importe: 30000 }]) {
      await request(app.getHttpServer()).post(path).set('Authorization', 'Bearer token')
        .send(withMonthly(invalid)).expect(400);
    }
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it('conserva conflicto y rechaza respuestas remotas invalidas',async()=>{
    fetchMock.mockResolvedValue(new Response('{}',{status:409}));await request(app.getHttpServer()).post(path).set('Authorization','Bearer token').send(value).expect(409);
    fetchMock.mockResolvedValue(new Response('{"version":0,"datos":{}}'));await request(app.getHttpServer()).get(path).set('Authorization','Bearer token').expect(502);
  });
});
