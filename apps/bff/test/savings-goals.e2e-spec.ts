import { Test } from '@nestjs/testing';
import { type INestApplication } from '@nestjs/common';
import request from 'supertest';
import { randomUUID } from 'node:crypto';
import { AppModule } from '../src/app.module.js';
import { AuthService } from '../src/auth.service.js';
describe('Metas de ahorro HTTP',()=>{
  let app:INestApplication;let remote:ReturnType<typeof vi.fn>;
  const space=randomUUID(),id=randomUUID(),account=randomUUID(),path=`/api/spaces/${space}/savings-goals`;
  const payload={id,cuenta_id:account,nombre:'Vacaciones',moneda:'ARS',objetivo:'100.00',fecha_objetivo:null};
  const row={...payload,espacio_id:space,cuenta_nombre:'Ahorros',archivada:false,version:0,saldo:'25.00',acumulado:'25.00',faltante:'75.00',porcentaje:'25.0',alcanzada:false,vencida:false};
  beforeEach(async()=>{
    const module=await Test.createTestingModule({imports:[AppModule]}).overrideProvider(AuthService).useValue({verifyIdentity:vi.fn().mockResolvedValue(randomUUID())}).compile();
    app=module.createNestApplication();await app.init();vi.stubEnv('API_BASE_URL','https://api.example');
    remote=vi.fn().mockImplementation(async()=>new Response(JSON.stringify(row)));vi.stubGlobal('fetch',remote);
  });
  afterEach(async()=>{await app.close();vi.unstubAllEnvs();vi.unstubAllGlobals();});
  it('exige autenticacion y conserva objetivo decimal sin cache',async()=>{
    await request(app.getHttpServer()).post(path).send(payload).expect(401);expect(remote).not.toHaveBeenCalled();
    await request(app.getHttpServer()).post(path).set('Authorization','Bearer token').send(payload).expect(200).expect(row).expect('Cache-Control','no-store');
    expect(JSON.parse(remote.mock.calls[0][1].body)).toEqual(payload);
  });
  it('rechaza dinero numerico, version booleana y reasignaciones',async()=>{
    for(const bad of [{...payload,objetivo:100},{...payload,objetivo:'0'},{...payload,usuario_id:randomUUID()}]){
      await request(app.getHttpServer()).post(path).set('Authorization','Bearer token').send(bad).expect(400);
    }
    for(const bad of [{nombre:'Casa',objetivo:'100',fecha_objetivo:null,version:true,archivada:false},
      {nombre:'Casa',objetivo:'100',fecha_objetivo:null,version:0,archivada:false,cuenta_id:randomUUID()}]){
      await request(app.getHttpServer()).patch(path+'/'+id).set('Authorization','Bearer token').send(bad).expect(400);
    }
    expect(remote).not.toHaveBeenCalled();
  });
  it('edita y archiva con version, conserva conflictos y filtra archivadas',async()=>{
    const edit={nombre:'Vacaciones',objetivo:'100.00',fecha_objetivo:null,version:0,archivada:true};
    remote.mockImplementation(async()=>new Response(JSON.stringify({...row,archivada:true,version:1})));
    await request(app.getHttpServer()).patch(path+'/'+id).set('Authorization','Bearer token').send(edit).expect(200);
    expect(remote.mock.calls[0][1].method).toBe('PATCH');
    remote.mockImplementation(async()=>new Response('{}',{status:409}));
    await request(app.getHttpServer()).patch(path+'/'+id).set('Authorization','Bearer token').send(edit).expect(409);
    remote.mockImplementation(async()=>new Response(JSON.stringify({items:[{...row,archivada:true}],next_offset:null})));
    await request(app.getHttpServer()).get(path).set('Authorization','Bearer token').expect(502);
    await request(app.getHttpServer()).get(path+'?archived=true').set('Authorization','Bearer token').expect(200);
  });
  it('rechaza progreso incoherente, respuesta ajena y objetivos alterados',async()=>{
    for(const bad of [{...row,acumulado:'50.00'},{...row,porcentaje:'100.0'},{...row,espacio_id:randomUUID()},{...row,cuenta_id:randomUUID()}]){
      remote.mockImplementation(async()=>new Response(JSON.stringify(bad)));
      await request(app.getHttpServer()).post(path).set('Authorization','Bearer token').send(payload).expect(502);
    }
  });
  it('admite saldo negativo y exceso con progreso acotado',async()=>{
    for(const changes of [{saldo:'-10.00',acumulado:'0.00',faltante:'100.00',porcentaje:'0.0',alcanzada:false},
      {saldo:'120.00',acumulado:'120.00',faltante:'0.00',porcentaje:'100.0',alcanzada:true}]){
      const value={...row,...changes};remote.mockImplementation(async()=>new Response(JSON.stringify({items:[value],next_offset:null})));
      await request(app.getHttpServer()).get(path).set('Authorization','Bearer token').expect(200).expect({items:[value],next_offset:null});
    }
  });
});
