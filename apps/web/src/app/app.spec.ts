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
      register: vi.fn().mockResolvedValue('check-email'), confirmRegistration: vi.fn().mockResolvedValue(true),
      resetPassword: vi.fn().mockResolvedValue('updated'), endPasswordRecovery: vi.fn(),
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
  it('deshabilita el registro con menos de ocho caracteres', async () => {
    const { fixture, auth } = setup();
    [...fixture.nativeElement.querySelectorAll('button')].find(button => button.textContent.trim() === 'Crear cuenta').click();
    fixture.detectChanges();
    const fill = async (field: string, value: string) => {
      const input = fixture.nativeElement.querySelector('#register-' + field);
      input.value = value;
      input.dispatchEvent(new Event('input'));
      await fixture.whenStable();
      fixture.detectChanges();
    };
    await fill('email', 'test@example.com');
    await fill('password', 'short');
    const submit = fixture.nativeElement.querySelector('button[type=submit]');
    expect(submit.disabled).toBe(true);
    await fill('password', 'example-password');
    expect(submit.disabled).toBe(false);
    submit.click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(auth.register).toHaveBeenCalledWith('test@example.com', 'example-password', expect.stringContaining('?registro=1'));
    expect(fixture.nativeElement.textContent).toContain('Si recibís un correo de Piggo');
  });

  it('quita el token de confirmación del URL y espera a que se pulse el botón', async () => {
    window.history.replaceState(null, '', '/?registro=1#token_hash=sample-signup');
    const { fixture, auth } = setup();
    expect(window.location.search + window.location.hash).toBe('');
    expect(auth.confirmRegistration).not.toHaveBeenCalled();
    fixture.nativeElement.querySelector('button').click();
    await fixture.whenStable();
    expect(auth.confirmRegistration).toHaveBeenCalledWith('sample-signup');
  });
  it('abre un enlace de recuperación, limpia la URL y permite elegir contraseña', async () => {
    window.history.replaceState(null, '', '/?recuperar=1#token_hash=sample-hash');
    const { fixture, auth } = setup();
    await fixture.whenStable();
    expect(window.location.search).toBe('');
    expect(window.location.hash).toBe('');
    expect(fixture.nativeElement.querySelector('h1').textContent).toContain('contraseña nueva');
    for (const id of ['new-password', 'repeat-password']) {
      const input = fixture.nativeElement.querySelector('#' + id);
      input.value = 'new-test-password';
      input.dispatchEvent(new Event('input'));
    }
    await fixture.whenStable();
    fixture.nativeElement.querySelector('form').dispatchEvent(new Event('submit', { cancelable: true }));
    await fixture.whenStable();
    fixture.detectChanges();
    expect(auth.resetPassword).toHaveBeenCalledWith('sample-hash', 'new-test-password');
    expect(fixture.nativeElement.textContent).toContain('Contraseña actualizada');
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
