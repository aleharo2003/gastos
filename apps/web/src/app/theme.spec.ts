import { TestBed } from '@angular/core/testing';
import { afterEach, vi } from 'vitest';
import { Theme } from './theme';

describe('Preferencia de tema', () => {
  afterEach(() => { vi.restoreAllMocks(); localStorage.removeItem('gastos.theme'); delete document.documentElement.dataset['theme']; });
  it('recupera una preferencia guardada y permite volver al dispositivo', () => {
    localStorage.setItem('gastos.theme', 'dark');
    const theme = TestBed.inject(Theme);
    expect(document.documentElement.dataset['theme']).toBe('dark');
    theme.set('system');
    expect(localStorage.getItem('gastos.theme')).toBe('system');
    expect(theme.mode()).toBe('system');
  });
  it('ignora valores no admitidos', () => {
    localStorage.setItem('gastos.theme', 'invalid');
    const theme = TestBed.inject(Theme);
    expect(theme.mode()).toBe('system');
    theme.set('invalid');
    expect(document.documentElement.dataset['theme']).toBe('system');
  });
  it('funciona aunque el navegador impida guardar preferencias', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked'); });
    const theme = TestBed.inject(Theme);
    expect(() => theme.set('light')).not.toThrow();
    expect(document.documentElement.dataset['theme']).toBe('light');
  });
});
