import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { App } from 'supertest/types.js';
import { AppModule } from './../src/app.module.js';

describe('AppController (e2e)', () => {
  let app: INestApplication<App>;

  beforeEach(async () => {
    vi.stubEnv('API_TIMEOUT_MS', undefined);
    vi.stubEnv('RENDER_GIT_COMMIT', undefined);
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('FastAPI no disponible')));

    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    await app.init();
  });

  afterEach(async () => {
    await app.close();
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it('/ conserva el saludo inicial', () => {
    return request(app.getHttpServer()).get('/').expect(200).expect('Hello World!');
  });

  it('/health responde sin consultar FastAPI', async () => {
    await request(app.getHttpServer()).get('/health').expect(200).expect({ status: 'ok' });
    expect(fetch).not.toHaveBeenCalled();
  });

  it('/version devuelve null sin un commit configurado', async () => {
    await request(app.getHttpServer())
      .get('/version')
      .expect(200)
      .expect('Cache-Control', 'no-store')
      .expect({ commit: null });
    expect(fetch).not.toHaveBeenCalled();
  });

  it('/version informa el commit del despliegue', () => {
    vi.stubEnv('RENDER_GIT_COMMIT', 'commit-de-prueba');
    return request(app.getHttpServer()).get('/version').expect(200).expect({ commit: 'commit-de-prueba' });
  });

  it('/api/hello devuelve el 502 controlado si FastAPI falla', async () => {
    const response = await request(app.getHttpServer()).get('/api/hello').expect(502);
    expect(response.body).toMatchObject({
      statusCode: 502,
      message: 'No se pudo consultar FastAPI',
    });
  });
});
