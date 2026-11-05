import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { vi } from 'vitest';
import type { Session, SupabaseClient } from '@supabase/supabase-js';
import { AuthSession, AUTH_CLIENT_FACTORY } from './auth-session';

describe('AuthSession', () => {
  const session = { access_token: 'test-token', user: { id: 'user-1', email: 'test@example.com' } } as Session;
  let http: HttpTestingController;
  let service: AuthSession;
  let event: (event: string, session: Session | null) => void;
  let auth: any;
  beforeEach(() => {
    auth = {
      onAuthStateChange: vi.fn((callback) => { event = callback; return { data: { subscription: { unsubscribe: vi.fn() } } }; }),
      getSession: vi.fn().mockResolvedValue({ data: { session: null }, error: null }),
      signInWithPassword: vi.fn().mockResolvedValue({ data: { session }, error: null }),
      signOut: vi.fn().mockResolvedValue({ error: null }),
      startAutoRefresh: vi.fn().mockResolvedValue(undefined),
      stopAutoRefresh: vi.fn().mockResolvedValue(undefined),
    };
    TestBed.configureTestingModule({ providers: [
      provideHttpClient(), provideHttpClientTesting(),
      { provide: AUTH_CLIENT_FACTORY, useValue: async () => ({ auth }) as unknown as SupabaseClient },
    ] });
    service = TestBed.inject(AuthSession); http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => { http.verify(); localStorage.clear(); });
  async function initialize() {
    const pending = service.initialize();
    http.expectOne('/auth-config.json').flush({ projectRef: 'cyxhyfbiacfayixbmotq', publishableKey: 'sb_publishable_test' });
    await pending;
  }
  it('rechaza configuracion incompleta', async () => {
    const pending = service.initialize();
    http.expectOne('/auth-config.json').flush({ projectRef: '', publishableKey: '' });
    await pending;
    expect(service.available()).toBe(false); expect(service.ready()).toBe(true);
  });
  it('restaura la sesion y exige identidad coincidente del BFF', async () => {
    auth.getSession.mockResolvedValue({ data: { session }, error: null });
    await initialize();
    const request = http.expectOne('/api/me');
    expect(request.request.headers.get('Authorization')).toBe('Bearer test-token');
    request.flush({ usuario_id: 'user-1' }); await Promise.resolve();
    expect(service.verified()).toBe(true);
  });
  it('rechaza una identidad distinta', async () => {
    await initialize(); await service.login('test@example.com', 'password');
    http.expectOne('/api/me').flush({ usuario_id: 'other-user' }); await Promise.resolve();
    expect(service.verified()).toBe(false); expect(service.message()).toContain('No pudimos');
  });
  it('credenciales incorrectas no llaman al BFF', async () => {
    await initialize();
    auth.signInWithPassword.mockResolvedValue({ data: { session: null }, error: { message: 'private detail' } });
    await service.login('test@example.com', 'wrong');
    http.expectNone('/api/me');
    expect(service.message()).not.toContain('private detail'); expect(service.signedIn()).toBe(false);
  });
  it('ignora respuestas tardias despues de salir y limpia almacenamiento', async () => {
    await initialize(); await service.login('test@example.com', 'password');
    const request = http.expectOne('/api/me');
    localStorage.setItem('gastos-auth-cyxhyfbiacfayixbmotq', 'test');
    await service.logout(); request.flush({ usuario_id: 'user-1' }); await Promise.resolve();
    expect(service.signedIn()).toBe(false); expect(service.verified()).toBe(false);
    expect(localStorage.getItem('gastos-auth-cyxhyfbiacfayixbmotq')).toBeNull();
    expect(auth.signOut).toHaveBeenCalledWith({ scope: 'local' });
  });
  it('renueva el token usado para verificar', async () => {
    await initialize();
    event('TOKEN_REFRESHED', { ...session, access_token: 'renewed' });
    const request = http.expectOne('/api/me');
    expect(request.request.headers.get('Authorization')).toBe('Bearer renewed');
    request.flush({ usuario_id: 'user-1' }); await Promise.resolve();
    expect(service.verified()).toBe(true);
  });
  it('permite reintentar un fallo de red', async () => {
    await initialize(); await service.login('test@example.com', 'password');
    http.expectOne('/api/me').flush({}, { status: 502, statusText: 'Bad Gateway' }); await Promise.resolve();
    expect(service.checking()).toBe(false); expect(service.verified()).toBe(false);
    const retry = service.verify(); http.expectOne('/api/me').flush({ usuario_id: 'user-1' });
    await retry; expect(service.verified()).toBe(true);
  });
});
