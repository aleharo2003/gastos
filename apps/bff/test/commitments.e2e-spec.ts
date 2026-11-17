import { Test } from '@nestjs/testing';
import { type INestApplication } from '@nestjs/common';
import request from 'supertest';
import { randomUUID } from 'node:crypto';
import { AppModule } from '../src/app.module.js';
import { AuthService } from '../src/auth.service.js';
describe('Deudas y pagos HTTP',()=>{
  let app:INestApplication;let remote:ReturnType<typeof vi.fn>;
  const space=randomUUID(),id=randomUUID(),account=randomUUID(),quota=randomUUID(),base=`/api/spaces/${space}`;
  const payload={id,cuenta_id:account,nombre:'Casa',moneda:'USD',importe:'250.00',categoria:'vivienda',primer_vencimiento:'2026-11-30',total_cuotas:10};
  const row={...payload,espacio_id:space,cuotas_pagadas:0,total:'2500.00',pagado:'0.00',pendiente:'2500.00',proximo_vencimiento:'2026-11-30'};
  const installment={id:quota,espacio_id:space,compromiso_id:id,numero:1,vencimiento:'2026-11-30',importe:'250.00',pagado:'30.00',pendiente:'220.00',estado:'parcial',vencida:false};
  const pay={id:randomUUID(),cuenta_id:account,fecha:'2026-11-17',importe:'30.00'};
  const payment={...pay,espacio_id:space,cuota_id:quota,moneda:'USD'};
  beforeEach(async()=>{
    const module=await Test.createTestingModule({imports:[AppModule]}).overrideProvider(AuthService).useValue({verifyIdentity:vi.fn().mockResolvedValue(randomUUID())}).compile();
    app=module.createNestApplication();await app.init();vi.stubEnv('API_BASE_URL','https://api.example');
    remote=vi.fn().mockImplementation(async()=>new Response(JSON.stringify(row)));vi.stubGlobal('fetch',remote);
  });
  afterEach(async()=>{await app.close();vi.unstubAllEnvs();vi.unstubAllGlobals();});
  it('exige token y reenvia el plan sin convertir dinero',async()=>{
    await request(app.getHttpServer()).post(base+'/commitments').send(payload).expect(401);expect(remote).not.toHaveBeenCalled();
    await request(app.getHttpServer()).post(base+'/commitments').set('Authorization','Bearer token').send(payload).expect(200).expect(row).expect('Cache-Control','no-store');
    expect(JSON.parse(remote.mock.calls[0][1].body)).toEqual(payload);
  });
  it('rechaza monto numerico, cuotas booleanas y campos ajenos',async()=>{
    for(const bad of [{...payload,importe:250},{...payload,total_cuotas:true},{...payload,total_cuotas:0},{...payload,usuario_id:randomUUID()}]){
      await request(app.getHttpServer()).post(base+'/commitments').set('Authorization','Bearer token').send(bad).expect(400);
    }
    await request(app.getHttpServer()).post(base+'/installments/'+quota+'/payments').set('Authorization','Bearer token').send({...pay,moneda:'ARS'}).expect(400);
    expect(remote).not.toHaveBeenCalled();
  });
  it('valida progreso y cuotas parciales sin aceptar datos ajenos',async()=>{
    remote.mockImplementation(async()=>new Response(JSON.stringify({items:[installment],next_offset:null})));
    await request(app.getHttpServer()).get(base+'/commitments/'+id+'/installments').set('Authorization','Bearer token').expect(200);
    for(const bad of [{...installment,pendiente:'219.00'},{...installment,compromiso_id:randomUUID()},{...installment,estado:'pagada'}]){
      remote.mockImplementation(async()=>new Response(JSON.stringify({items:[bad],next_offset:null})));
      await request(app.getHttpServer()).get(base+'/commitments/'+id+'/installments').set('Authorization','Bearer token').expect(502);
    }
    remote.mockImplementation(async()=>new Response(JSON.stringify({...row,total:'2499.00'})));
    await request(app.getHttpServer()).post(base+'/commitments').set('Authorization','Bearer token').send(payload).expect(502);
  });
  it('conserva pago, cuenta e identificador, y permite leer comprobantes desde el gasto',async()=>{
    const url=base+'/installments/'+quota+'/payments';
    remote.mockImplementation(async()=>new Response(JSON.stringify(payment)));
    await request(app.getHttpServer()).post(url).set('Authorization','Bearer token').send(pay).expect(200).expect(payment);
    expect(JSON.parse(remote.mock.calls[0][1].body)).toEqual(pay);
    remote.mockImplementation(async()=>new Response(JSON.stringify({items:[payment],next_offset:null})));
    await request(app.getHttpServer()).get(url+'?offset=0').set('Authorization','Bearer token').expect(200);
    remote.mockImplementation(async()=>new Response(JSON.stringify({...payment,cuenta_id:randomUUID()})));
    await request(app.getHttpServer()).post(url).set('Authorization','Bearer token').send(pay).expect(502);
  });
  it('propaga permisos y conflictos y rechaza paginas invalidas',async()=>{
    for(const status of [403,404,409,422,503]){
      remote.mockImplementation(async()=>new Response('{}',{status}));
      await request(app.getHttpServer()).post(base+'/installments/'+quota+'/payments').set('Authorization','Bearer token').send(pay).expect(status);
    }
    await request(app.getHttpServer()).get(base+'/commitments?offset=-1').set('Authorization','Bearer token').expect(400);
  });
});
