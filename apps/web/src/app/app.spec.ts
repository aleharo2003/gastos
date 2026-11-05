import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { vi } from 'vitest';
import { App } from './app';
import { AuthSession } from './auth-session';

describe('Login web', () => {
  function setup() {
    const auth = {
      ready: signal(true), available: signal(true), busy: signal(false),
      checking: signal(false), signedIn: signal(false), verified: signal(false),
      email: signal(''), message: signal(''), personalSpace: signal(''), creatingSpace: signal(false), createPersonalSpace: vi.fn(),
      initialize: vi.fn().mockResolvedValue(undefined),
      login: vi.fn().mockResolvedValue(undefined), logout: vi.fn(), verify: vi.fn(),
    };
    TestBed.configureTestingModule({ imports: [App], providers: [{ provide: AuthSession, useValue: auth }] });
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    return { fixture, auth };
  }
  it('deshabilita el ingreso sin credenciales', async () => {
    const { fixture } = setup(); await fixture.whenStable(); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('button').disabled).toBe(true);
  });
  it('envia credenciales y limpia la contraseña del formulario', async () => {
    const { fixture, auth } = setup(); await fixture.whenStable();
    for (const [id, value] of [['email', 'test@example.com'], ['password', 'example-password']]) {
      const input = fixture.nativeElement.querySelector('#' + id);
      input.value = value; input.dispatchEvent(new Event('input'));
    }
    await fixture.whenStable(); fixture.detectChanges();
    fixture.nativeElement.querySelector('form').dispatchEvent(new Event('submit', { cancelable: true }));
    await fixture.whenStable(); fixture.detectChanges();
    expect(auth.login).toHaveBeenCalledWith('test@example.com', 'example-password');
    expect(fixture.nativeElement.querySelector('#password').value).toBe('');
  });
  it('muestra la identidad verificada y permite salir', () => {
    const { fixture, auth } = setup();
    auth.signedIn.set(true); auth.verified.set(true); auth.email.set('test@example.com');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Tu sesión está verificada');
    fixture.nativeElement.querySelector('button.secondary').click();
    expect(auth.logout).toHaveBeenCalled();
  });
  it('muestra el error con una accion para reintentar', () => {
    const { fixture, auth } = setup();
    auth.signedIn.set(true); auth.message.set('No pudimos conectar');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role=alert]').textContent).toContain('No pudimos conectar');
    fixture.nativeElement.querySelector('button').click();
    expect(auth.verify).toHaveBeenCalled();
  });
});
