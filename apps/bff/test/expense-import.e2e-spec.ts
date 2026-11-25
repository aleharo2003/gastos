import { Test } from '@nestjs/testing';
import type { INestApplication } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import request from 'supertest';
import { AppModule } from '../src/app.module.js';
import { AuthService } from '../src/auth.service.js';

describe('Importación de movimientos', () => {
  let app: INestApplication;
  let upstream: ReturnType<typeof vi.fn>;
  const space = randomUUID();
  const account = randomUUID();
  const path = '/api/spaces/' + space + '/accounts/' + account + '/expense-import';

  beforeEach(async () => {
    const module = await Test.createTestingModule({ imports: [AppModule] }).overrideProvider(AuthService)
      .useValue({ verifyIdentity: vi.fn().mockResolvedValue(randomUUID()) }).compile();
    app = module.createNestApplication();
    await app.init();
    vi.stubEnv('API_BASE_URL', 'https://api.example');
    upstream = vi.fn().mockImplementation(async () => new Response('{"items":[]}'));
    vi.stubGlobal('fetch', upstream);
  });

  afterEach(async () => {
    await app.close();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it('reenvía el filtro de ingresos tanto al listar como al anular lotes', async () => {
    const batch = randomUUID();
    await request(app.getHttpServer()).get(path + '?tipo=ingreso').set('Authorization', 'Bearer test').expect(200);
    await request(app.getHttpServer()).post(path + '/' + batch + '/void?tipo=ingreso')
      .set('Authorization', 'Bearer test').expect(201);
    const urls = upstream.mock.calls.map(([url]) => new URL(String(url)));
    expect(urls.map(url => url.searchParams.get('tipo'))).toEqual(['ingreso', 'ingreso']);
    expect(urls[1].pathname).toBe('/spaces/' + space + '/accounts/' + account + '/expense-import/' + batch + '/void');
  });

  it('rechaza un tipo desconocido antes de consultar el servicio', async () => {
    await request(app.getHttpServer()).get(path + '?tipo=transferencia').set('Authorization', 'Bearer test').expect(400);
    expect(upstream).not.toHaveBeenCalled();
  });
});
