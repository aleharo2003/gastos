import { Test } from '@nestjs/testing';
import { UnauthorizedException, type INestApplication } from '@nestjs/common';
import request from 'supertest';
import { randomUUID } from 'node:crypto';
import { AppModule } from '../src/app.module.js';
import { AuthService } from '../src/auth.service.js';

describe('Cuentas HTTP', () => {
  let app: INestApplication;
  let fetchMock: ReturnType<typeof vi.fn>;
  let verify: ReturnType<typeof vi.fn>;
  const space = randomUUID(), id = randomUUID();
  const path = `/api/spaces/${space}/accounts`;
  const row = { id, espacio_id: space, nombre: 'Efectivo' };
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
  it('valida token antes de consultar', async () => {
    verify.mockRejectedValue(new UnauthorizedException());
    await request(app.getHttpServer()).get(path).set('Authorization','Bearer invalid').expect(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it('reenvia solo cuenta y token y conserva el ID del reintento', async () => {
    await request(app.getHttpServer()).post(path).set('Authorization','Bearer token')
      .send({ id, nombre:' Efectivo ' }).expect(200).expect(row).expect('Cache-Control','no-store');
    expect(verify).toHaveBeenCalledWith('token');
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toBe(`https://api.example/spaces/${space}/accounts?offset=0`);
    expect(JSON.parse(options.body)).toEqual({ id, nombre:'Efectivo' });
    expect(options.headers.Authorization).toBe('Bearer token');
  });
  it('rechaza identidad suministrada por el cliente', async () => {
    await request(app.getHttpServer()).post(path).set('Authorization','Bearer token')
      .send({ id, nombre:'Efectivo', usuario_id:randomUUID() }).expect(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it.each([403,409,503])('conserva error %s sin datos privados', async status => {
    fetchMock.mockResolvedValue(new Response('private details',{status}));
    const result = await request(app.getHttpServer()).get(path).set('Authorization','Bearer token').expect(status);
    expect(result.text).not.toContain('private details');
  });
  it('rechaza respuesta de otro espacio', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ ...row, espacio_id:randomUUID() })));
    await request(app.getHttpServer()).post(path).set('Authorization','Bearer token').send({ id, nombre:'Efectivo' }).expect(502);
  });
  it('lista una pagina valida', async () => {
    const page = {items:[row],next_offset:null};
    fetchMock.mockResolvedValue(new Response(JSON.stringify(page)));
    await request(app.getHttpServer()).get(path).set('Authorization','Bearer token').expect(200).expect(page);
  });
});
