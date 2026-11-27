import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { AuthSession } from './auth-session';
import { ReminderPreferences } from './reminder-preferences';

describe('Preferencias de recordatorios', () => {
  it('consulta al abrir la pestaña y permite desactivar conservando los ajustes', async () => {
    const settings = {
      canal: 'email', dias_anticipacion: 5, hora_local: '18:45',
      vencimientos: true, vencidas: true, resumen_semanal: false,
    };
    const saved = { ...settings, canal: 'ninguno' };
    const request = vi.fn().mockResolvedValueOnce(settings).mockResolvedValueOnce(saved);
    TestBed.configureTestingModule({
      imports: [ReminderPreferences],
      providers: [{ provide: AuthSession, useValue: { accountRequest: request } }],
    });
    const fixture = TestBed.createComponent(ReminderPreferences);
    fixture.componentRef.setInput('space', 'shared');
    fixture.detectChanges();
    expect(request).not.toHaveBeenCalled();
    fixture.componentRef.setInput('active', true);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    await fixture.whenStable();
    fixture.detectChanges();
    const screen = fixture.nativeElement as HTMLElement;
    const channel = screen.querySelector<HTMLSelectElement>('#reminder-channel')!;
    expect(channel.value).toBe('email');
    channel.value = 'ninguno';
    channel.dispatchEvent(new Event('change', { bubbles: true }));
    await fixture.whenStable();
    fixture.detectChanges();
    expect(screen.textContent).toContain('El envío por correo o push está desactivado.');
    screen.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await fixture.whenStable();
    fixture.detectChanges();

    expect(request.mock.calls).toEqual([
      ['GET', '/api/spaces/shared/reminder-preferences'],
      ['POST', '/api/spaces/shared/reminder-preferences', saved],
    ]);
    expect(screen.textContent).toContain('Preferencias guardadas.');
    expect(screen.querySelector<HTMLInputElement>('#reminder-time')!.value).toBe('18:45');
  });
});
