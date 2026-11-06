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
});
