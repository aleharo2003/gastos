import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { AuthSession } from './auth-session';
import { Movements } from './movements';

describe('Paginación de Movimientos', () => {
  afterEach(() => vi.unstubAllGlobals());

  async function setup(accountRequest: ReturnType<typeof vi.fn>) {
    const callbacks: Array<() => void> = [];
    vi.stubGlobal('IntersectionObserver', class {
      constructor(callback: IntersectionObserverCallback) {
        callbacks.push(() => callback([{ isIntersecting: true } as IntersectionObserverEntry], this as unknown as IntersectionObserver));
      }
      observe() {}
      disconnect() {}
    });
    TestBed.configureTestingModule({
      imports: [Movements],
      providers: [{ provide: AuthSession, useValue: { accountRequest } }],
    });
    const fixture = TestBed.createComponent(Movements);
    fixture.componentRef.setInput('space', 'test-space');
    const refresh = async () => {
      fixture.detectChanges();
      await fixture.whenStable();
      fixture.detectChanges();
    };
    await refresh();
    return { component: fixture.componentInstance, callbacks, refresh };
  }

  const page = (from: number, count: number, next_cursor: string | null) => ({
    items: Array.from({ length: count }, (_, offset) => ({
      id: String(from + offset), fecha: '2026-11-25', tipo: 'ingreso',
      descripcion: 'Ingreso', moneda: 'ARS', importe: '1.00', origen: null, destino: 'Banco', categoria: 'sueldo',
    })),
    next_cursor, totales: [],
  });

  it('agrega más de cien movimientos al bajar, manteniendo el filtro de ingreso', async () => {
    const request = vi.fn()
      .mockResolvedValueOnce(page(0, 0, null))
      .mockResolvedValueOnce(page(0, 50, 'a'))
      .mockResolvedValueOnce(page(50, 50, 'b'))
      .mockResolvedValueOnce(page(100, 1, null));
    const { component, callbacks, refresh } = await setup(request);
    component.filters.categoria = 'ingreso:sueldo';
    await component.load();
    await refresh();
    callbacks.at(-1)!();
    await refresh();
    callbacks.at(-1)!();
    await refresh();
    expect(component.items()).toHaveLength(101);
    expect(component.next()).toBeNull();
    expect(request.mock.calls.slice(1).map(([, path]) => new URL(path, 'https://piggo.example').search))
      .toEqual(['?categoria_ingreso=sueldo', '?categoria_ingreso=sueldo&cursor=a', '?categoria_ingreso=sueldo&cursor=b']);
  });

  it('permite el reintento manual después de un error', async () => {
    const request = vi.fn().mockResolvedValueOnce(page(0, 50, 'a'))
      .mockRejectedValueOnce(new Error('Falló la conexión')).mockResolvedValueOnce(page(50, 1, null));
    const { component, callbacks, refresh } = await setup(request);
    callbacks.at(-1)!();
    await refresh();
    expect(component.error()).toContain('Volvé a intentar');
    callbacks.at(-1)!();
    expect(request).toHaveBeenCalledTimes(2);
    await component.load(true);
    expect(component.items()).toHaveLength(51);
    expect(component.error()).toBe('');
  });

  it('anula una transferencia y vuelve a cargar el filtro que se estaba mostrando', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValueOnce(false).mockReturnValueOnce(true));
    const transfer = { ...page(7, 1, null).items[0], tipo: 'transferencia' as const, origen: 'Banco', destino: 'Efectivo' };
    const request = vi.fn()
      .mockResolvedValueOnce({ ...page(0, 0, null), items: [transfer] })
      .mockResolvedValueOnce({ id: transfer.id, anulado: true })
      .mockResolvedValueOnce(page(0, 0, null));
    const { component } = await setup(request);
    component.filters.texto = 'borrador sin aplicar';

    await component.confirmVoid(transfer);
    expect(request).toHaveBeenCalledTimes(1);

    await component.confirmVoid(transfer);
    expect(request).toHaveBeenNthCalledWith(2, 'POST', '/api/spaces/test-space/movements/transferencia/7/void');
    expect(request).toHaveBeenNthCalledWith(3, 'GET', '/api/spaces/test-space/movements?');
    expect(component.items()).toEqual([]);
    expect(component.voidNotice()).toBe('Transferencia anulada.');
  });
});
