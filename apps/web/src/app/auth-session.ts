import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { DestroyRef, inject, Injectable, InjectionToken, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import type { Session, SupabaseClient } from '@supabase/supabase-js';
import { environment } from '../environments/environment';

export const AUTH_CLIENT_FACTORY = new InjectionToken<(url: string, key: string, storageKey: string, persistSession?: boolean) => Promise<SupabaseClient>>('AUTH_CLIENT_FACTORY', {
  providedIn: 'root', factory: () => async (url, key, storageKey, persistSession = true) => {
    const { createClient } = await import('@supabase/supabase-js');
    return createClient(url, key, { auth: {
      storageKey, persistSession, autoRefreshToken: persistSession, detectSessionInUrl: false,
    } });
  },
});

@Injectable({ providedIn: 'root' })
export class AuthSession {
  readonly ready = signal(false);
  readonly available = signal(false);
  readonly busy = signal(false);
  readonly checking = signal(false);
  readonly signedIn = signal(false);
  readonly verified = signal(false);
  readonly email = signal('');
  readonly personalSpace = signal('');
  readonly personalSpaceId = signal('');
  readonly creatingSpace = signal(false);
  readonly message = signal('');
  private readonly http = inject(HttpClient);
  private readonly factory = inject(AUTH_CLIENT_FACTORY);
  private readonly destroy = inject(DestroyRef);
  private client?: SupabaseClient;
  private session: Session | null = null;
  private generation = 0;
  private started = false;
  private signingOut = false;
  private storageKey = '';
  private recoveryFactory?: () => Promise<SupabaseClient>;
  private recoveryClient?: SupabaseClient;
  private autoSpaceUser?: string;

  async requestPasswordReset(email: string, redirectTo: string): Promise<void> {
    await this.client?.auth.resetPasswordForEmail(email.trim(), { redirectTo }).catch(() => undefined);
  }

  async resetPassword(token: string, password: string): Promise<'updated' | 'expired' | 'retry'> {
    try {
      if (!this.recoveryClient) {
        const client = await this.recoveryFactory?.();
        if (!client) return 'retry';
        const { data, error } = await client.auth.verifyOtp({ type: 'recovery', token_hash: token });
        if (error || !data.session) {
          return error?.status === 400 || error?.status === 403 || error?.status === 422 ? 'expired' : 'retry';
        }
        this.recoveryClient = client;
      }
      const { error } = await this.recoveryClient.auth.updateUser({ password });
      if (error) return 'retry';
      await this.endPasswordRecovery();
      return 'updated';
    } catch {
      return 'retry';
    }
  }

  async endPasswordRecovery(): Promise<void> {
    const client = this.recoveryClient;
    this.recoveryClient = undefined;
    await client?.auth.signOut({ scope: 'local' }).catch(() => undefined);
  }

  get userId(): string | undefined {
    return this.session?.user.id;
  }

  async initialize(): Promise<void> {
    if (this.started) return;
    this.started = true;
    try {
      const config = await firstValueFrom(this.http.get<{ projectRef: string; publishableKey: string }>('/auth-config.json', { timeout: 10000 }));
      if (!/^[a-z0-9]{20}$/.test(config.projectRef) || !config.publishableKey?.startsWith('sb_publishable_')) throw new Error();
      this.storageKey = `gastos-auth-${config.projectRef}`;
      this.client = await this.factory(`https://${config.projectRef}.supabase.co`, config.publishableKey, this.storageKey);
      this.recoveryFactory = () => this.factory(
        `https://${config.projectRef}.supabase.co`, config.publishableKey, this.storageKey + '-recovery', false,
      );
      const subscription = this.client.auth.onAuthStateChange((_event, session) => {
        if (!this.signingOut) this.acceptSession(session);
      }).data.subscription;
      this.destroy.onDestroy(() => { subscription.unsubscribe(); void this.client?.auth.stopAutoRefresh().catch(() => {}); this.generation++; });
      const { data, error } = await this.client.auth.getSession();
      if (error) throw error;
      this.available.set(true);
      this.acceptSession(data.session);
    } catch {
      this.message.set('El inicio de sesión no está disponible en este momento.');
    } finally { this.ready.set(true); }
  }

  async register(email: string, password: string, emailRedirectTo: string): Promise<'signed-in' | 'check-email' | 'retry'> {
    if (!this.client || this.busy() || this.signedIn() || password.length < 8) return 'retry';
    this.busy.set(true);
    this.signingOut = false;
    try {
      const { data, error } = await this.client.auth.signUp({ email: email.trim(), password, options: { emailRedirectTo } });
      if (error || !data.session) return 'check-email';
      this.acceptRegisteredSession(data.session);
      return 'signed-in';
    } catch {
      return 'retry';
    } finally { this.busy.set(false); }
  }

  async confirmRegistration(token: string): Promise<boolean> {
    if (!this.client || this.busy() || this.signedIn() || !token) return false;
    this.busy.set(true);
    this.signingOut = false;
    try {
      const { data, error } = await this.client.auth.verifyOtp({ type: 'email', token_hash: token });
      if (error || !data.session) return false;
      this.acceptRegisteredSession(data.session);
      return true;
    } catch {
      return false;
    } finally { this.busy.set(false); }
  }

  private acceptRegisteredSession(session: Session): void {
    this.autoSpaceUser = session.user.id;
    this.acceptSession(session);
    if (this.verified() && !this.personalSpace()) void this.createPersonalSpace();
    void this.client?.auth.startAutoRefresh().catch(() => {});
  }

  private acceptSession(session: Session | null): void {
    if (session?.access_token && session.access_token === this.session?.access_token) return;
    this.generation++;
    const sameUser = !!session && session.user.id === this.session?.user.id;
    this.session = session;
    if (this.autoSpaceUser !== session?.user.id) this.autoSpaceUser = undefined;
    if (!sameUser) {
      this.personalSpace.set('');
      this.personalSpaceId.set('');
    }
    this.creatingSpace.set(false);
    this.signedIn.set(!!session);
    this.email.set(session?.user.email ?? '');
    this.verified.set(false);
    this.checking.set(false);
    if (session) void this.verify();
  }

  async login(email: string, password: string): Promise<void> {
    if (!this.client || this.busy()) return;
    this.busy.set(true);
    this.message.set('');
    this.signingOut = false;
    try {
      const { data, error } = await this.client.auth.signInWithPassword({ email: email.trim(), password });
      if (error || !data.session) {
        this.message.set('No pudimos iniciar sesión. Revisá el email y la contraseña.');
        return;
      }
      this.acceptSession(data.session);
      void this.client.auth.startAutoRefresh().catch(() => {});
    } catch {
      this.message.set('No pudimos conectar. Revisá tu conexión e intentá nuevamente.');
    } finally { this.busy.set(false); }
  }

  async verify(): Promise<void> {
    if (!this.session) return;
    const session = this.session;
    const revision = ++this.generation;
    this.checking.set(true);
    this.verified.set(false);
    this.message.set('');
    try {
      const identity = await firstValueFrom(this.http.get<{ usuario_id: string }>(`${environment.bffBaseUrl}/api/me`, {
        headers: { Authorization: `Bearer ${session.access_token}` }, timeout: environment.requestTimeoutMs,
      }));
      if (revision !== this.generation) return;
      if (identity.usuario_id !== session.user.id) throw new Error();
      this.verified.set(true);
      if (this.autoSpaceUser === session.user.id && !this.personalSpace()) void this.createPersonalSpace();
    } catch (error) {
      if (revision !== this.generation) return;
      this.message.set(error instanceof HttpErrorResponse && error.status === 401
        ? 'Tu sesión no pudo validarse. Cerrá sesión y volvé a ingresar.'
        : 'No pudimos conectar con Piggo. Podés volver a intentarlo.');
    } finally { if (revision === this.generation) this.checking.set(false); }
  }

  async createPersonalSpace(): Promise<void> {
    if (!this.session || !this.verified() || this.creatingSpace()) return;
    const session = this.session;
    this.creatingSpace.set(true);
    this.message.set('');
    try {
      const result = await firstValueFrom(this.http.post<{ usuario_id: string; espacio_id: string; nombre: string }>(
        `${environment.bffBaseUrl}/api/personal-space`, {}, {
          headers: { Authorization: `Bearer ${session.access_token}` }, timeout: environment.requestTimeoutMs,
        }));
      if (this.session !== session) return;
      if (result.usuario_id !== session.user.id || result.espacio_id !== session.user.id || !result.nombre) throw new Error();
      this.personalSpaceId.set(result.espacio_id);
      this.personalSpace.set(result.nombre);
    } catch {
      if (this.session === session) this.message.set('No pudimos preparar tu espacio. Volvé a intentarlo.');
    } finally {
      if (this.session === session) this.creatingSpace.set(false);
    }
  }

  async accountRequest<T>(method: 'GET' | 'POST' | 'PATCH', path: string, body?: unknown): Promise<T> {
    const session = this.session;
    if (!session || !this.verified()) throw new Error('Sesion no disponible');
    const result = await firstValueFrom(this.http.request<T>(method, `${environment.bffBaseUrl}${path}`, {
      body, headers: { Authorization: `Bearer ${session.access_token}` }, timeout: environment.requestTimeoutMs,
    }));
    if (this.session !== session) throw new Error('La sesion cambio');
    return result;
  }

  async uploadReceipt<T>(path: string, file: File): Promise<T> {
    const session=this.session;
    if(!session||!this.verified()) throw new Error('Sesion no disponible');
    const result=await firstValueFrom(this.http.post<T>(`${environment.bffBaseUrl}${path}`,file,{
      headers:{Authorization:`Bearer ${session.access_token}`,'Content-Type':'application/octet-stream','X-Receipt-Name':encodeURIComponent(file.name)},
      timeout:environment.requestTimeoutMs,
    }));
    if(this.session!==session) throw new Error('La sesion cambio');
    return result;
  }

  async downloadReceipt(path: string): Promise<Blob> {
    return this.downloadFile(path, environment.requestTimeoutMs);
  }

  async downloadSpaceExport(space: string): Promise<Blob> {
    return this.downloadFile('/api/spaces/' + encodeURIComponent(space) + '/export', 65_000);
  }

  private async downloadFile(path: string, timeout: number): Promise<Blob> {
    const session=this.session;
    if(!session||!this.verified()) throw new Error('Sesion no disponible');
    const result=await firstValueFrom(this.http.get(`${environment.bffBaseUrl}${path}`,{
      headers:{Authorization:`Bearer ${session.access_token}`},responseType:'blob',timeout,
    }));
    if(this.session!==session) throw new Error('La sesion cambio');
    return result;
  }

  async logout(): Promise<void> {
    if (!this.client || this.busy()) return;
    this.busy.set(true);
    this.signingOut = true;
    this.acceptSession(null);
    this.message.set('');
    try {
      const { error } = await this.client.auth.signOut({ scope: 'local' });
      if (error) throw error;
    } catch {
      this.message.set('Sesión cerrada en este dispositivo. No pudimos confirmar el cierre remoto.');
    } finally {
      await this.client.auth.stopAutoRefresh().catch(() => {});
      try {
        localStorage.removeItem(this.storageKey);
        localStorage.removeItem(`${this.storageKey}-code-verifier`);
      } catch { this.message.set('No pudimos limpiar el almacenamiento. Cerrá esta ventana y borrá los datos del sitio.'); }
      this.busy.set(false);
    }
  }
}
