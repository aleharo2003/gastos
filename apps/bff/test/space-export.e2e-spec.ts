import { Test } from '@nestjs/testing';
import type { INestApplication } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import request from 'supertest';
import { AppModule } from '../src/app.module.js';
import { AuthService } from '../src/auth.service.js';

describe('Exportación del espacio', () => {
  let app: INestApplication;
  let upstream: ReturnType<typeof vi.fn>;
  const space = randomUUID();
  const path = '/api/spaces/' + space + '/export';
  const archive = new Uint8Array(32);
  archive.set([0x50, 0x4b, 0x03, 0x04]);

  beforeEach(async () => {
    const module = await Test.createTestingModule({ imports: [AppModule] }).overrideProvider(AuthService)
      .useValue({ verifyIdentity: vi.fn().mockResolvedValue(randomUUID()) }).compile();
    app = module.createNestApplication();
    await app.init();
    vi.stubEnv('API_BASE_URL', 'https://api.example');
    upstream = vi.fn();
    vi.stubGlobal('fetch', upstream);
  });

  afterEach(async () => {
    await app.close();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it('exige una sesión', async () => {
    await request(app.getHttpServer()).get(path).expect(401).expect('WWW-Authenticate', 'Bearer');
    expect(upstream).not.toHaveBeenCalled();
  });

  it('entrega el archivo como descarga privada desde el espacio solicitado', async () => {
    upstream.mockResolvedValue(new Response(archive, { headers: { 'Content-Type': 'application/zip' } }));
    await request(app.getHttpServer()).get(path).set('Authorization', 'Bearer test')
      .expect(200).expect('Content-Type', 'application/zip').expect('Cache-Control', 'no-store')
      .expect('Content-Disposition', 'attachment; filename="piggo-datos.zip"');
    expect(String(upstream.mock.calls[0][0])).toBe('https://api.example/spaces/' + space + '/export');
  });

  it('conserva el rechazo de permisos y nunca descarga una respuesta inesperada', async () => {
    upstream.mockResolvedValueOnce(new Response(null, { status: 403 }));
    upstream.mockResolvedValueOnce(new Response('error', { headers: { 'Content-Type': 'application/zip' } }));
    await request(app.getHttpServer()).get(path).set('Authorization', 'Bearer test').expect(403);
    await request(app.getHttpServer()).get(path).set('Authorization', 'Bearer test').expect(502);
  });
});
