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
  it('conserva conflicto y rechaza respuestas remotas invalidas',async()=>{
    fetchMock.mockResolvedValue(new Response('{}',{status:409}));await request(app.getHttpServer()).post(path).set('Authorization','Bearer token').send(value).expect(409);
    fetchMock.mockResolvedValue(new Response('{"version":0,"datos":{}}'));await request(app.getHttpServer()).get(path).set('Authorization','Bearer token').expect(502);
  });
});
