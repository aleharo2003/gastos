import { Test } from '@nestjs/testing';
import { UnauthorizedException, type INestApplication } from '@nestjs/common';
import request from 'supertest';
import { randomUUID } from 'node:crypto';
import { AppModule } from '../src/app.module.js';
import { AuthService } from '../src/auth.service.js';

describe('Gastos HTTP', () => {
  let app: INestApplication;
  let fetchMock: ReturnType<typeof vi.fn>;
  let verify: ReturnType<typeof vi.fn>;
  const space = randomUUID(), id = randomUUID(), account = randomUUID();
  const path = `/api/spaces/${space}/accounts/${account}/expenses`;
  const payload = { id, fecha:'2026-11-06', descripcion:'Supermercado', moneda:'USD', importe:'0.10' };
  const row = { ...payload, espacio_id:space, cuenta_id:account };
  beforeEach(async () => {
    verify = vi.fn().mockResolvedValue(randomUUID());
    const module = await Test.createTestingModule({ imports: [AppModule] })
      .overrideProvider(AuthService).useValue({ verifyIdentity: verify }).compile();
    app = module.createNestApplication(); await app.init();
    vi.stubEnv('API_BASE_URL', 'https://api.example');
    fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(row)));
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(async () => { await app.close(); vi.unstubAllEnvs(); vi.unstubAllGlobals(); });
  it('reenvia filtros codificados y conserva categoria',async()=>{
    const page={items:[{...row,categoria:'alimentos'}],next_offset:null};
    fetchMock.mockResolvedValue(new Response(JSON.stringify(page)));
    await request(app.getHttpServer()).get(path).query({texto:'10% & cerveza',desde:'2026-11-01',hasta:'2026-11-10',categoria:'alimentos',moneda:'ARS',offset:100}).set('Authorization','Bearer token').expect(200).expect(page);
    const url=new URL(String(fetchMock.mock.calls[0][0]));
    expect(url.searchParams.get('texto')).toBe('10% & cerveza');expect(url.searchParams.get('offset')).toBe('100');
    expect(url.searchParams.get('categoria')).toBe('alimentos');
  });
  it('acepta categoria al crear y rechaza categorias arbitrarias',async()=>{
    fetchMock.mockResolvedValue(new Response(JSON.stringify({...row,categoria:'ocio'})));
    await request(app.getHttpServer()).post(path).set('Authorization','Bearer token').send({...payload,categoria:'ocio'}).expect(200);
    await request(app.getHttpServer()).post(path).set('Authorization','Bearer token').send({...payload,categoria:'inventada'}).expect(400);
  });
  it('rechaza filtros desconocidos, repetidos o demasiado largos',async()=>{
    for(const query of ['categoria=inventada','texto=a&texto=b','usuario_id=other','moneda=XXX','texto='+ 'x'.repeat(161)]) {
      await request(app.getHttpServer()).get(path+'?'+query).set('Authorization','Bearer token').expect(400);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('conserva la etiqueta aproximada y reenvia el modo de busqueda',async()=>{
    const page={items:[{...row,coincidencia_aproximada:true}],next_offset:null};
    fetchMock.mockResolvedValue(new Response(JSON.stringify(page)));
    await request(app.getHttpServer()).get(path).query({texto:'serbesa',aproximada:'true'}).set('Authorization','Bearer token').expect(200).expect(page);
    const url=new URL(String(fetchMock.mock.calls[0][0]));expect(url.searchParams.get('aproximada')).toBe('true');
    expect(url.searchParams.get('texto')).toBe('serbesa');
  });
  it('rechaza modo invalido o repetido y etiqueta remota mal formada',async()=>{
    await request(app.getHttpServer()).get(path+'?aproximada=maybe').set('Authorization','Bearer token').expect(400);
    await request(app.getHttpServer()).get(path+'?aproximada=true&aproximada=false').set('Authorization','Bearer token').expect(400);
    expect(fetchMock).not.toHaveBeenCalled();
    fetchMock.mockResolvedValue(new Response(JSON.stringify({items:[{...row,coincidencia_aproximada:'true'}],next_offset:null})));
    await request(app.getHttpServer()).get(path).set('Authorization','Bearer token').expect(502);
  });
  it('consulta sugerencias con token y sin cache',async()=>{
    const result={categoria:'alimentos',coincidencias:2,total:3};
    fetchMock.mockResolvedValue(new Response(JSON.stringify(result)));
    await request(app.getHttpServer()).get(path+'/category-suggestion').query({descripcion:'Cerveza & pan'}).set('Authorization','Bearer token').expect(200).expect(result).expect('Cache-Control','no-store');
    const [url,options]=fetchMock.mock.calls[0];expect(new URL(String(url)).pathname).toBe(`/spaces/${space}/accounts/${account}/expenses/category-suggestion`);
    expect(new URL(String(url)).searchParams.get('descripcion')).toBe('Cerveza & pan');expect(options.headers.Authorization).toBe('Bearer token');
  });
  it('sugerencias exigen identidad y descripcion valida',async()=>{
    await request(app.getHttpServer()).get(path+'/category-suggestion?descripcion=Cerveza').expect(401);
    for(const query of ['descripcion=x','descripcion=a&descripcion=b','descripcion=Cerveza&usuario=otro']) {
      await request(app.getHttpServer()).get(path+'/category-suggestion?'+query).set('Authorization','Bearer token').expect(400);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('rechaza sugerencias remotas incoherentes',async()=>{
    for(const value of [{categoria:'secreto',coincidencias:2,total:2},{categoria:'ocio',coincidencias:1,total:1},{categoria:'ocio',coincidencias:2,total:10},{categoria:null,coincidencias:-1,total:0}]) {
      fetchMock.mockResolvedValue(new Response(JSON.stringify(value)));
      await request(app.getHttpServer()).get(path+'/category-suggestion?descripcion=Cerveza').set('Authorization','Bearer token').expect(502);
    }
  });
  it('permite ausencia de sugerencia y conserva denegaciones',async()=>{
    fetchMock.mockResolvedValue(new Response(JSON.stringify({categoria:null,coincidencias:0,total:0})));
    await request(app.getHttpServer()).get(path+'/category-suggestion?descripcion=Cerveza').set('Authorization','Bearer token').expect(200);
    fetchMock.mockResolvedValue(new Response('private',{status:403}));
    const result=await request(app.getHttpServer()).get(path+'/category-suggestion?descripcion=Cerveza').set('Authorization','Bearer token').expect(403);
    expect(result.text).not.toContain('private');
  });
  it('consulta similares con token y conserva importes y monedas',async()=>{
    const result={referencia_id:id,items:[{...row,id:randomUUID(),coincidencia_aproximada:true}]};
    fetchMock.mockResolvedValue(new Response(JSON.stringify(result)));
    await request(app.getHttpServer()).get(`${path}/${id}/similar`).set('Authorization','Bearer token').expect(200).expect(result).expect('Cache-Control','no-store');
    const [url,options]=fetchMock.mock.calls[0];expect(String(url)).toBe(`https://api.example/spaces/${space}/accounts/${account}/expenses/${id}/similar`);
    expect(options.method).toBe('GET');expect(options.headers.Authorization).toBe('Bearer token');
  });
  it('rechaza similares sin identidad o con ID invalido',async()=>{
    await request(app.getHttpServer()).get(`${path}/${id}/similar`).expect(401);
    await request(app.getHttpServer()).get(`${path}/invalid/similar`).set('Authorization','Bearer token').expect(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('rechaza referencias ajenas, duplicados y respuesta fuera de alcance',async()=>{
    const another={...row,id:randomUUID()};
    for(const value of [
      {referencia_id:randomUUID(),items:[]}, {referencia_id:id,items:[row]},
      {referencia_id:id,items:[another,another]}, {referencia_id:id,items:[{...another,cuenta_id:randomUUID()}]},
      {referencia_id:id,items:Array.from({length:6},()=>({...row,id:randomUUID()}))},
    ]) {
      fetchMock.mockResolvedValue(new Response(JSON.stringify(value)));
      await request(app.getHttpServer()).get(`${path}/${id}/similar`).set('Authorization','Bearer token').expect(502);
    }
  });
  it('conserva denegacion y ausencia del gasto sin detalles internos',async()=>{
    for(const status of [403,404]) {
      fetchMock.mockResolvedValue(new Response('private',{status}));
      const result=await request(app.getHttpServer()).get(`${path}/${id}/similar`).set('Authorization','Bearer token').expect(status);
      expect(result.text).not.toContain('private');
    }
  });
  it('requiere token', async () => {
    await request(app.getHttpServer()).get(path).expect(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('edita mediante PATCH con identidad y control de original', async () => {
    const body={original:payload,nuevo:{...payload,fecha:'2026-11-01'}};
    fetchMock.mockResolvedValue(new Response(JSON.stringify({...row,fecha:'2026-11-01'})));
    await request(app.getHttpServer()).patch(`${path}/${id}`).set('Authorization','Bearer token').send(body).expect(200);
    const [url,options]=fetchMock.mock.calls[0];
    expect(String(url)).toBe(`https://api.example/spaces/${space}/accounts/${account}/expenses/${id}`);
    expect(options.method).toBe('PATCH');expect(JSON.parse(options.body)).toEqual(body);
  });
  it('rechaza cambio de ID y campos de pertenencia en edicion',async()=>{
    await request(app.getHttpServer()).patch(`${path}/${id}`).set('Authorization','Bearer token')
      .send({original:payload,nuevo:{...payload,id:randomUUID()}}).expect(400);
    await request(app.getHttpServer()).patch(`${path}/${id}`).set('Authorization','Bearer token')
      .send({original:payload,nuevo:{...payload,espacio_id:randomUUID()}}).expect(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('valida token antes de consultar', async () => {
    verify.mockRejectedValue(new UnauthorizedException());
    await request(app.getHttpServer()).get(path).set('Authorization','Bearer invalid').expect(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('reenvia solo gasto y token y conserva el ID del reintento', async () => {
    await request(app.getHttpServer()).post(path).set('Authorization','Bearer token')
      .send(payload).expect(200).expect(row).expect('Cache-Control','no-store');
    expect(verify).toHaveBeenCalledWith('token');
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toBe(`https://api.example/spaces/${space}/accounts/${account}/expenses?offset=0`);
    expect(JSON.parse(options.body)).toEqual(payload);
    expect(options.headers.Authorization).toBe('Bearer token');
  });
  it('rechaza identidad suministrada por el cliente', async () => {
    await request(app.getHttpServer()).post(path).set('Authorization','Bearer token')
      .send({ ...payload, usuario_id:randomUUID() }).expect(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it.each([403,409,503])('conserva error %s sin datos privados', async status => {
    fetchMock.mockResolvedValue(new Response('private details',{status}));
    const result = await request(app.getHttpServer()).get(path).set('Authorization','Bearer token').expect(status);
    expect(result.text).not.toContain('private details');
  });
  it('rechaza respuesta de otro espacio', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ ...row, espacio_id:randomUUID() })));
    await request(app.getHttpServer()).post(path).set('Authorization','Bearer token').send(payload).expect(502);
  });
  it.each([0.1, '1.001', 'NaN', '-1', '0', '1e2'])('rechaza importe %s', async importe => {
    await request(app.getHttpServer()).post(path).set('Authorization','Bearer token').send({...payload,importe}).expect(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('lista una pagina valida', async () => {
    const page = {items:[row],next_offset:null};
    fetchMock.mockResolvedValue(new Response(JSON.stringify(page)));
    await request(app.getHttpServer()).get(path).set('Authorization','Bearer token').expect(200).expect(page);
  });

  it('lista todas las cuentas sin aceptar filas de otro espacio',async()=>{
    const globalPath=`/api/spaces/${space}/expenses`;
    const page={items:[row,{...row,id:randomUUID(),cuenta_id:randomUUID()}],next_offset:null};
    fetchMock.mockResolvedValue(new Response(JSON.stringify(page)));
    await request(app.getHttpServer()).get(globalPath).set('Authorization','Bearer token').expect(200).expect(page);
    expect(new URL(String(fetchMock.mock.calls[0][0])).pathname).toBe(`/spaces/${space}/expenses`);
    fetchMock.mockResolvedValue(new Response(JSON.stringify({items:[{...row,espacio_id:randomUUID()}],next_offset:null})));
    await request(app.getHttpServer()).get(globalPath).set('Authorization','Bearer token').expect(502);
    await request(app.getHttpServer()).post(globalPath).set('Authorization','Bearer token').send(payload).expect(404);
  });
  it('reenvia resumen completo y rechaza importes flotantes y parametros ajenos',async()=>{
    const globalPath=`/api/spaces/${space}/expense-summary`;
    const summary={fecha:'2026-11-11',mes:'2026-11',totales:[{moneda:'ARS',dia:'100.00',mes:'1234.50'}]};
    fetchMock.mockResolvedValue(new Response(JSON.stringify(summary)));
    await request(app.getHttpServer()).get(globalPath).expect(401);
    await request(app.getHttpServer()).get(globalPath).query({account}).set('Authorization','Bearer token').expect(200).expect(summary).expect('Cache-Control','no-store');
    expect(new URL(String(fetchMock.mock.calls[0][0])).searchParams.get('account')).toBe(account);
    await request(app.getHttpServer()).get(globalPath).query({usuario_id:randomUUID()}).set('Authorization','Bearer token').expect(400);
    fetchMock.mockResolvedValue(new Response(JSON.stringify({...summary,totales:[{moneda:'ARS',dia:0.1,mes:'1234.50'}]})));
    await request(app.getHttpServer()).get(globalPath).set('Authorization','Bearer token').expect(502);
  });
});
