import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { AuthSession } from './auth-session';
import { SpaceExport } from './space-export';

describe('Exportar mis datos', () => {
  function setup(downloadSpaceExport = vi.fn()) {
    TestBed.configureTestingModule({
      imports: [SpaceExport],
      providers: [{ provide: AuthSession, useValue: { downloadSpaceExport } }],
    });
    const fixture = TestBed.createComponent(SpaceExport);
    fixture.componentRef.setInput('space', 'test-space');
    fixture.detectChanges();
    return fixture.componentInstance;
  }

  it('evita solicitudes duplicadas y muestra el rechazo de permisos', async () => {
    let reject!: (error: unknown) => void;
    const request = vi.fn(() => new Promise<Blob>((_, fail) => { reject = fail; }));
    const component = setup(request);
    const running = component.download();
    await component.download();
    expect(request).toHaveBeenCalledExactlyOnceWith('test-space');
    expect(component.loading()).toBe(true);
    reject(new HttpErrorResponse({ status: 403 }));
    await running;
    expect(component.loading()).toBe(false);
    expect(component.error()).toContain('titular');
  });

  it('rechaza una respuesta que no es un ZIP', async () => {
    const component = setup(vi.fn().mockResolvedValue(new Blob(['error'], { type: 'text/plain' })));
    await component.download();
    expect(component.success()).toBe(false);
    expect(component.error()).toContain('Volvé a intentar');
  });
});
