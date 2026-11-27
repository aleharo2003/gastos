import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { AuthSession } from './auth-session';
import { PushDevice } from './push-device';

describe('Dispositivo push', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('solicita la suscripción solo al pulsar Activar y registra la baja', async () => {
    const keys = { p256dh: 'B' + 'A'.repeat(86), auth: 'A'.repeat(22) };
    const endpoint = 'https://fcm.googleapis.com/fcm/send/test';
    const subscription = { toJSON: () => ({ endpoint, keys }), unsubscribe: vi.fn().mockResolvedValue(true) };
    const pushManager = {
      getSubscription: vi.fn().mockResolvedValue(null), subscribe: vi.fn().mockResolvedValue(subscription),
    };
    const workers = { getRegistration: vi.fn().mockResolvedValue({ active: {}, pushManager }) };
    const previous = Object.getOwnPropertyDescriptor(navigator, 'serviceWorker');
    Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: workers });
    const browser = document.defaultView!;
    const securityContext = Object.getOwnPropertyDescriptor(browser, 'isSecureContext');
    Object.defineProperty(browser, 'isSecureContext', { configurable: true, value: true });
    vi.stubGlobal('Notification', { permission: 'granted' });
    vi.stubGlobal('PushManager', function PushManager() {});
    const request = vi.fn().mockResolvedValueOnce({ active: false, public_key: keys.p256dh })
      .mockResolvedValueOnce({ active: true }).mockResolvedValueOnce({ active: false });
    try {
      TestBed.configureTestingModule({
        imports: [PushDevice], providers: [{ provide: AuthSession, useValue: { accountRequest: request } }],
      });
      const fixture = TestBed.createComponent(PushDevice);
      fixture.componentRef.setInput('space', 'space');
      fixture.detectChanges();
      const screen = fixture.nativeElement as HTMLElement;
      await vi.waitFor(() => {
        fixture.detectChanges();
        expect(screen.textContent).toContain('Activar en este dispositivo');
      });
      expect(pushManager.subscribe).not.toHaveBeenCalled();
      screen.querySelector('button')!.click();
      expect(pushManager.subscribe).toHaveBeenCalledWith({ userVisibleOnly: true, applicationServerKey: expect.any(Uint8Array) });
      await vi.waitFor(() => {
        fixture.detectChanges();
        expect(screen.textContent).toContain('Dispositivo registrado');
      });
      const device = localStorage.getItem('piggo.push.device');
      expect(request).toHaveBeenNthCalledWith(2, 'POST', '/api/spaces/space/push-subscriptions',
        { device_id: device, subscription: { endpoint, keys } });
      screen.querySelector('button')!.click();
      await vi.waitFor(() => {
        fixture.detectChanges();
        expect(subscription.unsubscribe).toHaveBeenCalledOnce();
      });
      expect(request).toHaveBeenNthCalledWith(3, 'POST', '/api/spaces/space/push-subscriptions',
        { device_id: device, subscription: null });
      expect(subscription.unsubscribe).toHaveBeenCalledOnce();
      expect(screen.textContent).toContain('Dispositivo desactivado');
    } finally {
      if (securityContext) Object.defineProperty(browser, 'isSecureContext', securityContext);
      else Reflect.deleteProperty(browser, 'isSecureContext');
      if (previous) Object.defineProperty(navigator, 'serviceWorker', previous);
      else Reflect.deleteProperty(navigator, 'serviceWorker');
    }
  });
});
