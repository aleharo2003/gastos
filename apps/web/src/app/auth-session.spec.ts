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
  let recoveryAuth: any;
  let factory: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    auth = {
      onAuthStateChange: vi.fn((callback) => { event = callback; return { data: { subscription: { unsubscribe: vi.fn() } } }; }),
      getSession: vi.fn().mockResolvedValue({ data: { session: null }, error: null }),
      signUp: vi.fn().mockResolvedValue({ data: { session }, error: null }),
      verifyOtp: vi.fn().mockResolvedValue({ data: { session }, error: null }),
      signInWithPassword: vi.fn().mockResolvedValue({ data: { session }, error: null }),
      signOut: vi.fn().mockResolvedValue({ error: null }),
      resetPasswordForEmail: vi.fn().mockResolvedValue({ error: null }),
      startAutoRefresh: vi.fn().mockResolvedValue(undefined),
      stopAutoRefresh: vi.fn().mockResolvedValue(undefined),
    };
    recoveryAuth = {
      verifyOtp: vi.fn().mockResolvedValue({ data: { session }, error: null }),
      updateUser: vi.fn().mockResolvedValue({ error: null }),
      signOut: vi.fn().mockResolvedValue({ error: null }),
    };
    factory = vi.fn(async (_url, _key, _storageKey, persistSession = true) =>
      ({ auth: persistSession ? auth : recoveryAuth }) as unknown as SupabaseClient);
    TestBed.configureTestingModule({ providers: [
      provideHttpClient(), provideHttpClientTesting(),
      { provide: AUTH_CLIENT_FACTORY, useValue: factory },
    ] });
    service = TestBed.inject(AuthSession); http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => { http.verify(); localStorage.clear(); });
  async function initialize() {
    const pending = service.initialize();
    http.expectOne('/auth-config.json').flush({ projectRef: 'cyxhyfbiacfayixbmotq', publishableKey: 'sb_publishable_test' });
    await pending;
  }
  async function assertOnboarding() {
    http.expectOne('/api/me').flush({ usuario_id: 'user-1' });
    await Promise.resolve();
    const pending = http.expectOne('/api/personal-space');
    expect(pending.request.method).toBe('POST');
    expect(pending.request.headers.get('Authorization')).toBe('Bearer test-token');
    pending.flush({ usuario_id: 'user-1', espacio_id: 'user-1', nombre: 'Mi espacio' });
    await Promise.resolve();
    expect(service.personalSpace()).toBe('Mi espacio');
  }

  it('registra y prepara el espacio con una sesión que ya emitió SIGNED_IN', async () => {
    await initialize();
    auth.signUp.mockImplementationOnce(async () => {
      event('SIGNED_IN', session);
      return { data: { session }, error: null };
    });
    expect(await service.register(' test@example.com ', 'example-password', 'https://piggo.example/?registro=1')).toBe('signed-in');
    expect(auth.signUp).toHaveBeenCalledWith({
      email: 'test@example.com', password: 'example-password', options: { emailRedirectTo: 'https://piggo.example/?registro=1' },
    });
    await assertOnboarding();
  });

  it('presenta el mismo resultado al esperar confirmación y ante un email existente', async () => {
    await initialize();
    auth.signUp.mockResolvedValueOnce({ data: { session: null }, error: null })
      .mockResolvedValueOnce({ data: { session: null }, error: { message: 'private detail' } });
    for (let i = 0; i < 2; i++) {
      expect(await service.register('test@example.com', 'example-password', 'https://piggo.example/?registro=1')).toBe('check-email');
    }
    expect(service.signedIn()).toBe(false);
    http.expectNone('/api/me');
    http.expectNone('/api/personal-space');
  });

  it('confirma el email y abre el espacio con la sesión verificada', async () => {
    await initialize();
    expect(await service.confirmRegistration('signed-token')).toBe(true);
    expect(auth.verifyOtp).toHaveBeenCalledWith({ type: 'email', token_hash: 'signed-token' });
    await assertOnboarding();
  });

  it('solicita la recuperación sin exponer errores del proveedor', async () => {
    await initialize();
    auth.resetPasswordForEmail.mockRejectedValueOnce(new Error('private detail'));
    await expect(service.requestPasswordReset(' test@example.com ', 'https://piggo.example/?recuperar=1'))
      .resolves.toBeUndefined();
    expect(auth.resetPasswordForEmail).toHaveBeenCalledWith('test@example.com', {
      redirectTo: 'https://piggo.example/?recuperar=1',
    });
    expect(service.message()).toBe('');
  });

  it('cambia la contraseña en una sesión separada y rechaza un enlace usado', async () => {
    await initialize();
    expect(await service.resetPassword('test-hash', 'long-test-password')).toBe('updated');
    expect(factory).toHaveBeenLastCalledWith(expect.any(String), expect.any(String),
      expect.stringMatching(/-recovery$/), false);
    expect(recoveryAuth.verifyOtp).toHaveBeenCalledWith({ type: 'recovery', token_hash: 'test-hash' });
    expect(recoveryAuth.updateUser).toHaveBeenCalledWith({ password: 'long-test-password' });
    expect(recoveryAuth.signOut).toHaveBeenCalledWith({ scope: 'local' });
    expect(service.signedIn()).toBe(false);
    http.expectNone('/api/me');

    recoveryAuth.verifyOtp.mockResolvedValueOnce({ data: { session: null }, error: { status: 403 } });
    expect(await service.resetPassword('test-hash', 'another-test-password')).toBe('expired');
    expect(recoveryAuth.updateUser).toHaveBeenCalledTimes(1);
  });

  it('crea espacio con token y permite repetir sin duplicados de UI', async () => {
    await initialize(); await service.login('test@example.com', 'password');
    http.expectOne('/api/me').flush({ usuario_id: 'user-1' }); await Promise.resolve();
    const pending = service.createPersonalSpace();
    const request = http.expectOne('/api/personal-space');
    expect(request.request.method).toBe('POST');
    expect(request.request.headers.get('Authorization')).toBe('Bearer test-token');
    request.flush({ usuario_id: 'user-1', espacio_id: 'user-1', nombre: 'Mi espacio' });
    await pending; expect(service.personalSpace()).toBe('Mi espacio');
    await service.logout(); expect(service.personalSpace()).toBe('');
  });
  it('ignora alta que llega despues de cerrar sesion', async () => {
    await initialize(); await service.login('test@example.com', 'password');
    http.expectOne('/api/me').flush({ usuario_id: 'user-1' }); await Promise.resolve();
    const pending = service.createPersonalSpace();
    const request = http.expectOne('/api/personal-space');
    await service.logout();
    request.flush({ usuario_id: 'user-1', espacio_id: 'user-1', nombre: 'Mi espacio' });
    await pending; expect(service.personalSpace()).toBe('');
  });
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
