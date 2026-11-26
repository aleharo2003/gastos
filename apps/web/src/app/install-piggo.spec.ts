import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { InstallPiggo } from './install-piggo';

describe('InstallPiggo', () => {
  const visitKey = 'piggo.install.visits';

  beforeEach(() => localStorage.removeItem(visitKey));
  afterEach(() => {
    localStorage.removeItem(visitKey);
    vi.restoreAllMocks();
  });

  it('waits for a return visit and a click before showing the native install prompt', async () => {
    const prompt = vi.fn().mockResolvedValue(undefined);
    const offer = () => Object.assign(new Event('beforeinstallprompt', { cancelable: true }), { prompt });
    const firstVisit = TestBed.createComponent(InstallPiggo);
    window.dispatchEvent(offer());
    firstVisit.detectChanges();
    expect(firstVisit.nativeElement.querySelector('button')).toBeNull();
    expect(localStorage.getItem(visitKey)).toBe('1');
    firstVisit.destroy();

    const secondVisit = TestBed.createComponent(InstallPiggo);
    const event = offer();
    window.dispatchEvent(event);
    secondVisit.detectChanges();
    expect(event.defaultPrevented).toBe(true);
    expect(prompt).not.toHaveBeenCalled();
    secondVisit.nativeElement.querySelector('button').click();
    await secondVisit.whenStable();
    expect(prompt).toHaveBeenCalledOnce();
    expect(secondVisit.nativeElement.querySelector('button')).toBeNull();
  });

  it('shows the steps for adding Piggo to the home screen in Safari on iOS', () => {
    vi.spyOn(window.navigator, 'userAgent', 'get').mockReturnValue('Mozilla/5.0 (iPhone) Version/17.0 Safari/604.1');
    const fixture = TestBed.createComponent(InstallPiggo);
    fixture.detectChanges();
    const button = fixture.nativeElement.querySelector('button');
    const help = fixture.nativeElement.querySelector('#install-piggo-ios');
    expect(help.hidden).toBe(true);
    button.click();
    fixture.detectChanges();
    expect(button.getAttribute('aria-expanded')).toBe('true');
    expect(help.hidden).toBe(false);
    expect(help.textContent).toContain('Agregar a inicio');
  });
});
