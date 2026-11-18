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
  const row={...payload,variable:false,pausado:false,version:1,espacio_id:space,cuotas_pagadas:0,cuotas_no_aplican:0,total:'2500.00',pagado:'0.00',pendiente:'2500.00',proximo_vencimiento:'2026-11-30'};
  const installment={estimado:false,version:1,id:quota,espacio_id:space,compromiso_id:id,numero:1,vencimiento:'2026-11-30',importe:'250.00',pagado:'30.00',pendiente:'220.00',estado:'parcial',vencida:false};
  const pay={id:randomUUID(),cuenta_id:account,fecha:'2026-11-17',importe:'30.00'};
  const payment={...pay,espacio_id:space,cuota_id:quota,moneda:'USD'};
  beforeEach(async()=>{
    const module=await Test.createTestingModule({imports:[AppModule]}).overrideProvider(AuthService).useValue({verifyIdentity:vi.fn().mockResolvedValue(randomUUID())}).compile();
    app=module.createNestApplication();await app.init();vi.stubEnv('API_BASE_URL','https://api.example');
    remote=vi.fn().mockImplementation(async()=>new Response(JSON.stringify(row)));vi.stubGlobal('fetch',remote);
  });
  afterEach(async()=>{await app.close();vi.unstubAllEnvs();vi.unstubAllGlobals();});
  it('registra y consulta una variacion como decimal exacto, con autorizacion', async () => {
    const url = base + '/index-values';
    const value = { indice: 'CAC', periodo: '2026-10', variacion: '-0.1234' };
    await request(app.getHttpServer()).get(url).expect(401);
    await request(app.getHttpServer()).post(url).set('Authorization', 'Bearer token')
      .send({ ...value, variacion: -0.1234 }).expect(400);
    expect(remote).not.toHaveBeenCalled();

    remote.mockImplementation(async () => new Response(JSON.stringify(value)));
    await request(app.getHttpServer()).post(url).set('Authorization', 'Bearer token')
      .send(value).expect(200).expect(value).expect('Cache-Control', 'no-store');
    expect(JSON.parse(remote.mock.calls[0][1].body)).toEqual(value);

    const page = { items: [value], next_offset: null };
    remote.mockImplementation(async () => new Response(JSON.stringify(page)));
    await request(app.getHttpServer()).get(url + '?offset=100').set('Authorization', 'Bearer token')
      .expect(200).expect(page);
    expect(remote.mock.calls[1][0].pathname).toBe('/spaces/' + space + '/index-values');
    expect(remote.mock.calls[1][0].search).toBe('?offset=100');

    remote.mockImplementation(async () => new Response('{}', { status: 409 }));
    await request(app.getHttpServer()).post(url).set('Authorization', 'Bearer token')
      .send(value).expect(409);
  });
  it('importa un CSV en el espacio y devuelve el error por fila', async () => {
    const url = base + '/index-values/import';
    const body = { csv: 'indice,periodo,variacion\nCAC,2026-10,2.3456\n' };
    await request(app.getHttpServer()).post(url).send(body).expect(401);
    await request(app.getHttpServer()).post(url).set('Authorization', 'Bearer token')
      .send({ csv: 'a'.repeat(32769) }).expect(400);
    expect(remote).not.toHaveBeenCalled();

    const result = { importadas: 1, existentes: 0 };
    remote.mockImplementation(async () => new Response(JSON.stringify(result)));
    await request(app.getHttpServer()).post(url).set('Authorization', 'Bearer token')
      .send(body).expect(200).expect(result).expect('Cache-Control', 'no-store');
    expect(remote.mock.calls[0][0].pathname).toBe('/spaces/' + space + '/index-values/import');
    expect(JSON.parse(remote.mock.calls[0][1].body)).toEqual(body);

    const detail = 'Fila 2: el índice ya tiene otra variación para ese mes.';
    remote.mockImplementation(async () => new Response(JSON.stringify({ detail }), { status: 409 }));
    await request(app.getHttpServer()).post(url).set('Authorization', 'Bearer token')
      .send(body).expect(409).expect({ message: detail });
  });
  it('acepta un plan indexado con total generado distinto del importe base', async () => {
    const input = {...payload,indice_ajuste:'CAC'};
    const indexed = {...row,indice_ajuste:'CAC',total:'275.00',pendiente:'275.00'};
    remote.mockImplementation(async()=>new Response(JSON.stringify(indexed)));
    await request(app.getHttpServer()).post(base+'/commitments').set('Authorization','Bearer token')
      .send(input).expect(200).expect(indexed);
    expect(JSON.parse(remote.mock.calls[0][1].body)).toEqual(input);
    await request(app.getHttpServer()).post(base+'/commitments').set('Authorization','Bearer token')
      .send({...input,total_cuotas:null}).expect(400);
    const provisional = {...installment,estado:'pendiente',pagado:'0.00',pendiente:'250.00',pendiente_ajuste:true};
    const page = {items:[provisional],next_offset:null};
    remote.mockImplementation(async()=>new Response(JSON.stringify(page)));
    await request(app.getHttpServer()).get(base+'/commitments/'+id+'/installments')
      .set('Authorization','Bearer token').expect(200).expect(page);
  });
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
    const total={no_aplican:0,borradores:0,estimado:'0.00',moneda:'USD',cuotas:1,cuotas_pagadas:0,total:'250.00',pagado:'30.00',pendiente:'220.00',vencido:'0.00'};
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

  it('identifica borradores y confirma un lote sin aceptar campos ni ids ajenos',async()=>{
    const draft={...installment,estimado:true,estado:'borrador',pagado:'0.00',pendiente:'250.00',nombre:'Luz',moneda:'USD',cuenta_id:account};
    const page={borradores:101,items:[draft],next_offset:100};
    remote.mockImplementation(async()=>new Response(JSON.stringify(page)));
    await request(app.getHttpServer()).get(base+'/installment-drafts?offset=0').set('Authorization','Bearer token').expect(200).expect(page);
    remote.mockImplementation(async()=>new Response(JSON.stringify({...page,items:[{...draft,espacio_id:randomUUID()}]})));
    await request(app.getHttpServer()).get(base+'/installment-drafts').set('Authorization','Bearer token').expect(502);
    const payload={items:[{id:quota,importe:'300.00',version:1}]};
    remote.mockImplementation(async()=>new Response(JSON.stringify({confirmadas:[quota]})));
    await request(app.getHttpServer()).post(base+'/installment-confirmations').send(payload).expect(401);
    await request(app.getHttpServer()).post(base+'/installment-confirmations').set('Authorization','Bearer token').send(payload).expect(200).expect({confirmadas:[quota]});
    expect(JSON.parse(remote.mock.calls.at(-1)![1].body)).toEqual(payload);
    for(const bad of [{items:[]},{items:[...payload.items,...payload.items]},{items:[{...payload.items[0],importe:300}]},{...payload,usuario_id:randomUUID()}]){
      await request(app.getHttpServer()).post(base+'/installment-confirmations').set('Authorization','Bearer token').send(bad).expect(400);
    }
    remote.mockImplementation(async()=>new Response(JSON.stringify({confirmadas:[randomUUID()]})));
    await request(app.getHttpServer()).post(base+'/installment-confirmations').set('Authorization','Bearer token').send(payload).expect(502);
  });
  it('reenvia el tipo variable y rechaza variables con cuotas finitas',async()=>{
    const input={...payload,total_cuotas:null,variable:true};
    const result={...row,...input,total:'250.00',pendiente:'250.00'};
    remote.mockImplementation(async()=>new Response(JSON.stringify(result)));
    await request(app.getHttpServer()).post(base+'/commitments').set('Authorization','Bearer token').send(input).expect(200).expect(result);
    await request(app.getHttpServer()).post(base+'/commitments').set('Authorization','Bearer token').send({...input,total_cuotas:10}).expect(400);
  });

  it('permite cuotas variables pagadas por debajo del estimado inicial',async()=>{
    const paid={...row,variable:true,total_cuotas:null,total:'100.00',pagado:'100.00',pendiente:'0.00',cuotas_pagadas:1,proximo_vencimiento:null};
    remote.mockImplementation(async()=>new Response(JSON.stringify({items:[paid],next_offset:null})));
    await request(app.getHttpServer()).get(base+'/commitments').set('Authorization','Bearer token').expect(200).expect({items:[paid],next_offset:null});
  });

  it('marca una cuota como no aplicable y valida el acuse de la API',async()=>{
    const result={id:quota,estado:'no_aplica',version:2};
    const url=base+'/installments/'+quota+'/skip';
    remote.mockImplementation(async()=>new Response(JSON.stringify(result)));
    await request(app.getHttpServer()).post(url).set('Authorization','Bearer token').send({version:1}).expect(200).expect(result);
    await request(app.getHttpServer()).post(url).set('Authorization','Bearer token').send({version:1,importe:'0'}).expect(400);
    remote.mockImplementation(async()=>new Response(JSON.stringify({...result,version:3})));
    await request(app.getHttpServer()).post(url).set('Authorization','Bearer token').send({version:1}).expect(502);
  });
  it('expone el resumen de vencimientos con autenticación y valida su grupo',async()=>{
    const route=base+'/due-overview';
    const empty={cantidad:0,totales:[],items:[]};
    const item={id:quota,nombre:'Casa',numero:1,vencimiento:'2026-11-17',moneda:'USD',pendiente:'220.00',estimado:false,pendiente_ajuste:true};
    const data={fecha:'2026-11-17',fin_semana:'2026-11-22',
      grupos:{hoy:{cantidad:1,totales:[{moneda:'USD',pendiente:'220.00'}],items:[item]},semana:empty,vencidas:empty},
      resumen_mes:[{moneda:'USD',pendiente:'220.00',pagado:'30.00'}],
      saldos:['ARS','USD','EUR'].map(moneda=>({moneda,saldo:moneda==='ARS'?'-30.00':'0.00'})),
      presupuesto:{limites:{diario:{moneda:'ARS',importe:'100.00'},semanal:null},
        gastos:[{moneda:'ARS',dia:'30.00',semana:'30.00',mes:'30.00'}]}};
    const upstream={...data,saldos:{totales:data.saldos.map(row=>({...row,ingresos:'0.00',
      gastos:row.moneda==='ARS'?'30.00':'0.00'}))}};
    remote.mockImplementation(async()=>new Response(JSON.stringify(upstream)));
    await request(app.getHttpServer()).get(route).expect(401);
    await request(app.getHttpServer()).get(route).set('Authorization','Bearer token').expect(200).expect(data);
    await request(app.getHttpServer()).get(route+'?fecha=2026-11-17').set('Authorization','Bearer token').expect(400);
    data.presupuesto.gastos[0].semana='20.00';
    await request(app.getHttpServer()).get(route).set('Authorization','Bearer token').expect(502);
    data.presupuesto.gastos[0].semana='30.00';
    item.vencimiento='2026-11-16';
    await request(app.getHttpServer()).get(route).set('Authorization','Bearer token').expect(502);
  });
});
