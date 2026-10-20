import type { INestApplication } from '@nestjs/common';
import { Test } from '@nestjs/testing';
import request from 'supertest';
import type { App } from 'supertest/types.js';
import { AppModule } from '../src/app.module.js';
import { configureCors } from '../src/cors.config.js';

describe('CORS del BFF (e2e)', () => {
  let app: INestApplication<App> | undefined;
  const frontendOrigin = 'https://web.example.com';

  async function createApplication(origin: string | undefined) {
    vi.stubEnv('FRONTEND_ORIGIN', origin);
    vi.stubEnv('API_TIMEOUT_MS', undefined);
    const moduleFixture = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();
    app = moduleFixture.createNestApplication();
    configureCors(app);
    await app.init();
    return app.getHttpServer();
  }

  afterEach(async () => {
    await app?.close();
    app = undefined;
    vi.unstubAllEnvs();
  });

  it('permite al origen configurado leer la respuesta', async () => {
    const server = await createApplication(frontendOrigin);
    const response = await request(server)
      .get('/health')
      .set('Origin', frontendOrigin)
      .expect(200)
      .expect('Access-Control-Allow-Origin', frontendOrigin);
    expect(
      response.headers['access-control-allow-credentials'],
    ).toBeUndefined();
  });

  it('no permite a otro origen leer la respuesta mediante CORS', async () => {
    const server = await createApplication(frontendOrigin);
    const response = await request(server)
      .get('/health')
      .set('Origin', 'https://otro.example.com')
      .expect(200);
    expect(response.headers['access-control-allow-origin']).toBeUndefined();
  });

  it('responde al preflight GET del origen permitido sin habilitar credenciales', async () => {
    const server = await createApplication(frontendOrigin);
    const response = await request(server)
      .options('/health')
      .set('Origin', frontendOrigin)
      .set('Access-Control-Request-Method', 'GET')
      .expect(204)
      .expect('Access-Control-Allow-Origin', frontendOrigin)
      .expect('Access-Control-Allow-Methods', 'GET,HEAD');
    expect(
      response.headers['access-control-allow-credentials'],
    ).toBeUndefined();
  });

  it('mantiene las consultas sin Origin disponibles', async () => {
    const server = await createApplication(frontendOrigin);
    const response = await request(server)
      .get('/health')
      .expect(200)
      .expect({ status: 'ok' });
    expect(response.headers['access-control-allow-origin']).toBeUndefined();
  });

  it('deja CORS desactivado cuando FRONTEND_ORIGIN no existe', async () => {
    const server = await createApplication(undefined);
    const response = await request(server)
      .get('/health')
      .set('Origin', frontendOrigin)
      .expect(200);
    expect(response.headers['access-control-allow-origin']).toBeUndefined();
  });
});
