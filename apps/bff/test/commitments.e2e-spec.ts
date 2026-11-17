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
  const row={...payload,pausado:false,version:1,espacio_id:space,cuotas_pagadas:0,total:'2500.00',pagado:'0.00',pendiente:'2500.00',proximo_vencimiento:'2026-11-30'};
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
  it('consulta el mes y valida totales, moneda, aislamiento y paginacion',async()=>{
    const total={moneda:'USD',cuotas:1,cuotas_pagadas:0,total:'250.00',pagado:'30.00',pendiente:'220.00',vencido:'0.00'};
    const item={...installment,nombre:'Casa',cuenta_id:account,moneda:'USD'};
    const page={mes:'2026-11',items:[item],totales:[total],next_offset:null};
    const url=base+'/installments?month=2026-11&offset=0';
    remote.mockImplementation(async()=>new Response(JSON.stringify(page)));
    await request(app.getHttpServer()).get(url).expect(401);
    await request(app.getHttpServer()).get(url).set('Authorization','Bearer token').expect(200).expect(page).expect('Cache-Control','no-store');
    expect(String(remote.mock.calls[0][0])).toContain('/installments?offset=0&month=2026-11');
    for(const invalid of [{...page,mes:'2026-12'},{...page,totales:[{...total,pendiente:'219.00'}]},
      {...page,totales:[total,total]},{...page,items:[{...item,espacio_id:randomUUID()}]},
      {...page,items:[{...item,vencimiento:'2026-12-01'}]},{...page,totales:[{...total,vencido:'221.00'}]}]){
      remote.mockImplementation(async()=>new Response(JSON.stringify(invalid)));
      await request(app.getHttpServer()).get(url).set('Authorization','Bearer token').expect(502);
    }
  });
  it('rechaza meses invalidos y lee deudas fuera de la pagina visible',async()=>{
    for(const query of ['','?month=0000-01','?month=2026-13','?month=2026-1','?month=2026-11&offset=-1','?month=2026-11&extra=yes']){
      await request(app.getHttpServer()).get(base+'/installments'+query).set('Authorization','Bearer token').expect(400);
    }
    expect(remote).not.toHaveBeenCalled();
    await request(app.getHttpServer()).get(base+'/commitments/'+id).set('Authorization','Bearer token').expect(200).expect(row);
    remote.mockImplementation(async()=>new Response(JSON.stringify({...row,id:randomUUID()})));
    await request(app.getHttpServer()).get(base+'/commitments/'+id).set('Authorization','Bearer token').expect(502);
  });

  it('acepta gastos fijos indefinidos y valida el estado de pausa',async()=>{
    const input={...payload,total_cuotas:null};
    const active={...row,total_cuotas:null,total:'250.00',pendiente:'250.00'};
    remote.mockImplementation(async()=>new Response(JSON.stringify(active)));
    await request(app.getHttpServer()).post(base+'/commitments').set('Authorization','Bearer token').send(input).expect(200).expect(active);
    const paused={...active,pausado:true,version:2};
    remote.mockImplementation(async()=>new Response(JSON.stringify(paused)));
    await request(app.getHttpServer()).patch(base+'/commitments/'+id).set('Authorization','Bearer token').send({pausado:true,version:1}).expect(200).expect(paused);
    expect(remote.mock.calls.at(-1)![1].method).toBe('PATCH');
    expect(JSON.parse(remote.mock.calls.at(-1)![1].body)).toEqual({pausado:true,version:1});
    remote.mockImplementation(async()=>new Response(JSON.stringify({...paused,pausado:false})));
    await request(app.getHttpServer()).patch(base+'/commitments/'+id).set('Authorization','Bearer token').send({pausado:true,version:1}).expect(502);
    for(const invalid of [{pausado:'true',version:1},{pausado:true,version:true},{pausado:true,version:0},{pausado:true,version:1,importe:'100'}]){
      await request(app.getHttpServer()).patch(base+'/commitments/'+id).set('Authorization','Bearer token').send(invalid).expect(400);
    }
  });

});
