import { Test } from '@nestjs/testing';
import type { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { exportJWK, generateKeyPair, SignJWT } from 'jose';
import { randomUUID } from 'node:crypto';
import { AppModule } from '../src/app.module.js';

describe('GET /api/me', () => {
  let app: INestApplication;
  let token: string;
  let user: string;
  let apiFetch: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    const project = 'abcdefghijklmnopqrst';
    vi.stubEnv('AUTH_SUPABASE_PROJECT_REF', project);
    vi.stubEnv('API_BASE_URL', 'https://api.example');
    vi.stubEnv('API_TIMEOUT_MS', '5000');
    const pair = await generateKeyPair('ES256');
    const jwk = { ...await exportJWK(pair.publicKey), kid: 'one', alg: 'ES256', use: 'sig' };
    user = randomUUID(); const now = Math.floor(Date.now() / 1000);
    token = await new SignJWT({ iss: `https://${project}.supabase.co/auth/v1`, aud: 'authenticated',
      sub: user, session_id: randomUUID(), role: 'authenticated', is_anonymous: false,
      iat: now - 5, exp: now + 300 }).setProtectedHeader({ alg: 'ES256', kid: 'one' }).sign(pair.privateKey);
    apiFetch = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ usuario_id: user })));
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url, options) => {
      if (String(url).includes('/.well-known/jwks.json')) return new Response(JSON.stringify({ keys: [jwk] }));
      return apiFetch(url, options);
    }));
    const module = await Test.createTestingModule({ imports: [AppModule] }).compile();
    app = module.createNestApplication(); await app.init();
  });
  afterEach(async () => { await app.close(); vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

  it('reenvia el token original y comprueba identidad de FastAPI', async () => {
    await request(app.getHttpServer()).get('/api/me').set('Authorization', `Bearer ${token}`)
      .set('X-User-Id', randomUUID()).expect(200).expect('Cache-Control', 'no-store').expect({ usuario_id: user });
    expect(String(apiFetch.mock.calls[0][0])).toBe('https://api.example/me');
    expect(apiFetch.mock.calls[0][1]).toMatchObject({ redirect: 'error',
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' } });
    expect(apiFetch.mock.calls[0][1].headers['X-User-Id']).toBeUndefined();
  });

  it('no acepta headers de identidad sin token', async () => {
    await request(app.getHttpServer()).get('/api/me').set('X-User-Id', user)
      .expect(401).expect('WWW-Authenticate', 'Bearer').expect('Cache-Control', 'no-store');
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it('rechaza token invalido antes de llamar FastAPI', async () => {
    await request(app.getHttpServer()).get('/api/me').set('Authorization', 'Bearer invalid').expect(401);
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it.each([401, 503])('conserva el error %s de FastAPI', async (status) => {
    apiFetch.mockResolvedValue(new Response('PRIVATE BODY', { status }));
    const result = await request(app.getHttpServer()).get('/api/me').set('Authorization', `Bearer ${token}`).expect(status);
    expect(result.text).not.toContain('PRIVATE BODY');
    expect(result.headers['cache-control']).toBe('no-store');
  });

  it('rechaza identidad diferente en FastAPI', async () => {
    apiFetch.mockResolvedValue(new Response(JSON.stringify({ usuario_id: randomUUID() })));
    await request(app.getHttpServer()).get('/api/me').set('Authorization', `Bearer ${token}`).expect(502);
  });

  it('no publica detalles de errores de red', async () => {
    apiFetch.mockRejectedValue(new Error(token));
    const result = await request(app.getHttpServer()).get('/api/me').set('Authorization', `Bearer ${token}`).expect(502);
    expect(result.text).not.toContain(token);
  });

  it('requiere configuracion de autenticacion', async () => {
    vi.stubEnv('AUTH_SUPABASE_PROJECT_REF', undefined);
    await request(app.getHttpServer()).get('/api/me').set('Authorization', `Bearer ${token}`).expect(503);
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it('rechaza una redireccion de FastAPI', async () => {
    apiFetch.mockResolvedValue(new Response(null, { status: 302, headers: { Location: 'https://other.example' } }));
    await request(app.getHttpServer()).get('/api/me').set('Authorization', `Bearer ${token}`).expect(502);
    expect(apiFetch).toHaveBeenCalledTimes(1);
  });

  it('rechaza HTTP hacia servidores externos', async () => {
    vi.stubEnv('API_BASE_URL', 'http://other.example');
    await request(app.getHttpServer()).get('/api/me').set('Authorization', `Bearer ${token}`).expect(502);
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it('rechaza Authorization duplicado', async () => {
    await request(app.getHttpServer()).get('/api/me')
      .set('Authorization', [`Bearer ${token}`, `Bearer ${token}`] as unknown as string).expect(401);
    expect(apiFetch).not.toHaveBeenCalled();
  });
});
