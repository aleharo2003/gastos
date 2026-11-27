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
    return { fixture, component: fixture.componentInstance, callbacks, refresh };
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

  it('muestra una compra de dólares con las dos monedas y respeta la privacidad', async () => {
    const purchase = { ...page(7, 1, null).items[0], tipo: 'cambio', descripcion: 'Casa de cambio',
      origen: 'Pesos', destino: 'Dólares', moneda: 'ARS', importe: '160000.00',
      moneda_destino: 'USD', importe_destino: '100.00' };
    const request = vi.fn().mockResolvedValue({ ...page(0, 0, null), items: [purchase] });
    const { fixture, component, refresh } = await setup(request);
    const row = fixture.nativeElement.querySelector('ul.movement-list li');
    expect(row.textContent).toContain('Compra de USD');
    expect(row.textContent).toContain('Pesos → Dólares');
    expect(row.querySelector(':scope > strong').textContent).toContain('ARS');
    expect(row.querySelector(':scope > strong').textContent).toContain('→ USD');
    expect(row.querySelector('button').textContent).toContain('Anular');
    fixture.componentRef.setInput('amountsHidden', true);
    await refresh();
    expect(row.querySelector(':scope > strong').textContent).toContain('ARS •••• → USD ••••');
    component.filters.tipo = 'cambio';
    await component.load();
    expect(request).toHaveBeenLastCalledWith('GET', '/api/spaces/test-space/movements?tipo=cambio');
  });

  it('anula un cambio y lo muestra en el filtro de anulados', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true));
    const purchase = { id: '7', fecha: '2026-11-25', tipo: 'cambio' as const, descripcion: 'Compra prueba',
      moneda: 'ARS', importe: '160000.00', origen: 'Pesos', destino: 'Dólares',
      moneda_destino: 'USD', importe_destino: '100.00' };
    const request = vi.fn()
      .mockResolvedValueOnce({ ...page(0, 0, null), items: [purchase] })
      .mockResolvedValueOnce({ id: purchase.id, anulado: true })
      .mockResolvedValueOnce(page(0, 0, null))
      .mockResolvedValueOnce({ ...page(0, 0, null), items: [{ ...purchase, anulado: true }] });
    const { fixture, component, refresh } = await setup(request);
    await component.confirmVoid(purchase);
    expect(request).toHaveBeenNthCalledWith(2, 'POST', '/api/spaces/test-space/movements/cambio/7/void');
    expect(component.items()).toEqual([]);
    expect(component.voidNotice()).toBe('Cambio anulado.');
    component.filters.anulados = 'true';
    await component.load();
    await refresh();
    const row = fixture.nativeElement.querySelector('ul.movement-list li');
    expect(row.textContent).toContain('Anulado');
    expect(row.querySelector('button')).toBeNull();
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
