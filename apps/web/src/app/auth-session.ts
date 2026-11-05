import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { DestroyRef, inject, Injectable, InjectionToken, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import type { Session, SupabaseClient } from '@supabase/supabase-js';
import { environment } from '../environments/environment';

export const AUTH_CLIENT_FACTORY = new InjectionToken<(url: string, key: string, storageKey: string) => Promise<SupabaseClient>>('AUTH_CLIENT_FACTORY', {
  providedIn: 'root', factory: () => async (url, key, storageKey) => {
    const { createClient } = await import('@supabase/supabase-js');
    return createClient(url, key, { auth: {
      storageKey, persistSession: true, autoRefreshToken: true, detectSessionInUrl: false,
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

  async initialize(): Promise<void> {
    if (this.started) return;
    this.started = true;
    try {
      const config = await firstValueFrom(this.http.get<{ projectRef: string; publishableKey: string }>('/auth-config.json', { timeout: 10000 }));
      if (!/^[a-z0-9]{20}$/.test(config.projectRef) || !config.publishableKey?.startsWith('sb_publishable_')) throw new Error();
      this.storageKey = `gastos-auth-${config.projectRef}`;
      this.client = await this.factory(`https://${config.projectRef}.supabase.co`, config.publishableKey, this.storageKey);
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

  private acceptSession(session: Session | null): void {
    if (session?.access_token && session.access_token === this.session?.access_token) return;
    this.generation++;
    this.session = session;
    this.personalSpace.set('');
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
    } catch (error) {
      if (revision !== this.generation) return;
      this.message.set(error instanceof HttpErrorResponse && error.status === 401
        ? 'Tu sesión no pudo validarse. Cerrá sesión y volvé a ingresar.'
        : 'No pudimos conectar con Gastos. Podés volver a intentarlo.');
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
      this.personalSpace.set(result.nombre);
    } catch {
      if (this.session === session) this.message.set('No pudimos preparar tu espacio. Volvé a intentarlo.');
    } finally {
      if (this.session === session) this.creatingSpace.set(false);
    }
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
