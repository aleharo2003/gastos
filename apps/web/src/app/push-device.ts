import { Component, DestroyRef, DOCUMENT, inject, input, OnChanges, signal } from '@angular/core';
import { AuthSession } from './auth-session';

const deviceKey = 'piggo.push.device';

@Component({
  selector: 'app-push-device',
  template: `
    <h4>Notificaciones en este dispositivo</h4>
    @if (busy()) { <p role="status">Comprobando el dispositivo…</p> }
    @if (status()) { <p role="status">{{ status() }}</p> }
    @if (error()) { <p role="alert">{{ error() }}</p> }
    @if (canSubscribe()) {
      <button type="button" [disabled]="busy()" (click)="activate()">Activar en este dispositivo</button>
    }
    @if (registered()) {
      <button class="secondary" type="button" [disabled]="busy()" (click)="deactivate()">Desactivar en este dispositivo</button>
    } @else if (error() && !canSubscribe()) {
      <button class="secondary" type="button" [disabled]="busy()" (click)="load()">Volver a comprobar</button>
    }
  `,
})
export class PushDevice implements OnChanges {
  readonly space = input.required<string>();
  protected readonly busy = signal(false);
  protected readonly registered = signal(false);
  protected readonly canSubscribe = signal(false);
  protected readonly status = signal('');
  protected readonly error = signal('');
  private readonly auth = inject(AuthSession);
  private readonly browser = inject(DOCUMENT).defaultView;
  private readonly destroy = inject(DestroyRef);
  private generation = 0;
  private device = '';
  private registration?: ServiceWorkerRegistration;
  private subscription: PushSubscription | null = null;
  private key?: Uint8Array<ArrayBuffer>;

  ngOnChanges(): void {
    this.generation++;
    this.busy.set(false);
    this.registered.set(false);
    this.canSubscribe.set(false);
    this.registration = undefined;
    this.subscription = null;
    this.key = undefined;
    void this.load();
  }

  private get path(): string {
    return `/api/spaces/${encodeURIComponent(this.space())}/push-subscriptions`;
  }

  private current(generation: number): boolean {
    return !this.destroy.destroyed && this.generation === generation;
  }

  protected async load(): Promise<void> {
    if (this.busy()) return;
    const browser = this.browser;
    const workers = browser?.navigator.serviceWorker;
    this.error.set('');
    this.status.set('');
    if (!browser?.isSecureContext || !workers || typeof Notification === 'undefined' || typeof PushManager === 'undefined') {
      this.status.set('Abrí Piggo en un navegador compatible con notificaciones push.');
      return;
    }
    const generation = this.generation;
    this.busy.set(true);
    try {
      const saved = browser.localStorage.getItem(deviceKey);
      this.device = saved && /^[0-9a-f-]{36}$/i.test(saved) ? saved : browser.crypto.randomUUID();
      browser.localStorage.setItem(deviceKey, this.device);
      const [registration, state] = await Promise.all([
        workers.getRegistration(),
        this.auth.accountRequest<{ active: boolean; public_key: string | null }>(
          'GET', this.path + '?device=' + encodeURIComponent(this.device),
        ),
      ]);
      const subscription = await registration?.pushManager?.getSubscription() ?? null;
      if (!this.current(generation)) return;
      this.registration = registration;
      this.subscription = subscription;
      this.registered.set(state.active);
      this.key = state.public_key ? Uint8Array.from(
        browser.atob(state.public_key.replace(/-/g, '+').replace(/_/g, '/') + '='),
        char => char.charCodeAt(0),
      ) : undefined;
      this.canSubscribe.set(!!registration?.active && !!this.key && !(state.active && subscription));
      if (state.active && subscription) this.status.set('Dispositivo registrado para notificaciones push.');
      else if (!this.key) this.status.set('La activación push todavía no está disponible en este ambiente.');
      else if (!registration?.active) this.error.set('Piggo todavía está preparando el dispositivo. Volvé a comprobar.');
    } catch {
      if (this.current(generation)) this.error.set('No pudimos comprobar las notificaciones de este dispositivo.');
    } finally { if (this.current(generation)) this.busy.set(false); }
  }

  protected async activate(): Promise<void> {
    if (this.busy() || !this.registration?.pushManager || !this.key) return;
    const generation = this.generation;
    const path = this.path;
    this.busy.set(true);
    this.error.set('');
    try {
      // La solicitud al navegador parte del clic, antes de consultar al servidor.
      const subscription = this.subscription ?? await this.registration.pushManager.subscribe({
        userVisibleOnly: true, applicationServerKey: this.key,
      });
      if (!this.current(generation)) return;
      this.subscription = subscription;
      const { endpoint, keys } = subscription.toJSON();
      const result = await this.auth.accountRequest<{ active: boolean }>('POST', path, {
        device_id: this.device, subscription: { endpoint, keys },
      });
      if (!result?.active) throw new Error();
      if (!this.current(generation)) return;
      this.registered.set(true);
      this.canSubscribe.set(false);
      this.status.set('Dispositivo registrado para notificaciones push.');
    } catch {
      if (!this.current(generation)) return;
      this.error.set(Notification.permission === 'denied'
        ? 'El navegador bloqueó las notificaciones. Podés cambiar el permiso en la configuración del sitio.'
        : 'No pudimos registrar este dispositivo. Volvé a intentar.');
    } finally { if (this.current(generation)) this.busy.set(false); }
  }

  protected async deactivate(): Promise<void> {
    if (this.busy()) return;
    const generation = this.generation;
    this.busy.set(true);
    this.error.set('');
    try {
      const result = await this.auth.accountRequest<{ active: boolean }>('POST', this.path, {
        device_id: this.device, subscription: null,
      });
      if (result?.active !== false) throw new Error();
      if (!this.current(generation)) return;
      this.registered.set(false);
      this.status.set('Dispositivo desactivado.');
      this.canSubscribe.set(!!this.registration?.active && !!this.key);
      if (await this.subscription?.unsubscribe()) this.subscription = null;
    } catch {
      if (this.current(generation)) this.error.set('No pudimos completar la desactivación. Volvé a comprobar.');
    } finally { if (this.current(generation)) this.busy.set(false); }
  }
}
