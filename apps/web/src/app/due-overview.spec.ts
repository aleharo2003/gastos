import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { AuthSession } from './auth-session';
import { DueOverview } from './due-overview';

describe('Pagos desde Hoy', () => {
  const installment = {
    id: 'quota', nombre: 'Casa', numero: 1, vencimiento: '2026-11-17',
    moneda: 'ARS', pendiente: '100.00', estimado: false,
  };

  function overview(balance: string) {
    const empty = { cantidad: 0, totales: [], items: [] };
    return {
      fecha: '2026-11-17', fin_semana: '2026-11-22',
      grupos: {
        hoy: { cantidad: 1, totales: [{ moneda: 'ARS', pendiente: balance }],
          items: [{ ...installment, pendiente: balance }] },
        semana: empty, vencidas: empty,
      },
      resumen_mes: [],
      saldos: [{ moneda: 'ARS', saldo: '-35.50' }],
      presupuesto: {
        limites: { diario: { moneda: 'ARS', importe: '100.00' }, semanal: null },
        gastos: [{ moneda: 'USD', dia: '1.00', semana: '1.00', mes: '1.00' }],
      },
    };
  }

  async function setup() {
    localStorage.removeItem('gastos.totals.hidden');
    const request = vi.fn().mockResolvedValue(overview('100.00'));
    TestBed.configureTestingModule({
      imports: [DueOverview],
      providers: [{ provide: AuthSession, useValue: { accountRequest: request } }],
    });
    const fixture = TestBed.createComponent(DueOverview);
    fixture.componentRef.setInput('space', 'shared');
    fixture.componentRef.setInput('accounts', [{ id: 'bank', nombre: 'Banco' }]);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, component: fixture.componentInstance, request };
  }

  it('señala las cuotas pendientes de ajuste y bloquea el pago', async () => {
    const { fixture, component, request } = await setup();
    const data = overview('100.00');
    const pending = { ...installment, pendiente_ajuste: true };
    data.grupos.hoy.items = [pending];
    request.mockResolvedValueOnce(data);
    await component.load();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Pendiente de ajuste');
    expect(fixture.nativeElement.querySelector('li button')).toBeNull();
    component.startPayment(pending);
    expect(component.selected()).toBeNull();
  });

  it('registra un pago parcial y refresca el panel', async () => {
    const { fixture, component, request } = await setup();
    const changed = vi.fn();
    component.paymentSaved.subscribe(changed);
    fixture.nativeElement.querySelector('li button').click();
    fixture.detectChanges();
    await fixture.whenStable();
    expect(fixture.nativeElement.querySelector('#due-pay-amount').value).toBe('100.00');
    component.paymentAmount = '25,50';
    request.mockResolvedValueOnce({ id: 'payment' }).mockResolvedValueOnce(overview('74.50'));
    await component.pay();
    expect(request.mock.calls[1]).toEqual(['POST', '/api/spaces/shared/installments/quota/payments',
      expect.objectContaining({ cuenta_id: 'bank', importe: '25.50' })]);
    expect(component.overview()?.grupos.hoy.totales[0].pendiente).toBe('74.50');
    expect(component.selected()).toBeNull();
    expect(changed).toHaveBeenCalledTimes(1);
  });

  it('reintenta el mismo pago si se pierde la respuesta', async () => {
    const { fixture, component, request } = await setup();
    component.startPayment(installment);
    request.mockRejectedValueOnce(new HttpErrorResponse({ status: 502 }));
    await component.pay();
    expect(component.uncertain()).toBe(true);
    component.cancelPayment();
    fixture.componentRef.setInput('active', false);
    fixture.detectChanges();
    expect(component.selected()).toEqual(installment);
    request.mockResolvedValueOnce({ id: 'payment' }).mockResolvedValueOnce(overview('10.00'));
    await component.pay();
    expect(request.mock.calls[2]).toEqual(request.mock.calls[1]);
    expect(component.uncertain()).toBe(false);
  });

  it('bloquea estimados y montos superiores al pendiente', async () => {
    const { component, request } = await setup();
    component.startPayment({ ...installment, estimado: true });
    expect(component.selected()).toBeNull();
    component.startPayment(installment);
    component.paymentAmount = '101';
    await component.pay();
    expect(request).toHaveBeenCalledTimes(1);
    expect(component.paymentError()).toContain('no supere el saldo');
  });
  it('muestra los gastos de cada período en su moneda y oculta los importes', async () => {
    const { fixture, component, request } = await setup();
    const data = overview('100.00');
    data.presupuesto.gastos = [
      { moneda: 'ARS', dia: '12.00', semana: '50.00', mes: '150.00' },
      { moneda: 'USD', dia: '0.00', semana: '5.00', mes: '10.00' },
    ];
    request.mockResolvedValueOnce(data);
    await component.load();
    fixture.detectChanges();

    const panels: NodeListOf<HTMLElement> = fixture.nativeElement.querySelectorAll('.spending-period');
    expect(panels).toHaveLength(3);
    expect([...panels[0].querySelectorAll('dd')].map(value => value.textContent)).toEqual(['12,00', '0,00']);
    expect([...panels[1].querySelectorAll('dd')].map(value => value.textContent)).toEqual(['50,00', '5,00']);
    expect([...panels[2].querySelectorAll('dd')].map(value => value.textContent)).toEqual(['150,00', '10,00']);

    window.dispatchEvent(new CustomEvent('gastos-privacy', { detail: true }));
    fixture.detectChanges();
    expect([...panels[2].querySelectorAll('dd')].map(value => value.textContent)).toEqual(['••••', '••••']);
  });

  it('consolida activos, saldos negativos y cuotas pendientes', async () => {
    const { fixture, component, request } = await setup();
    request.mockResolvedValue({
      ...overview('100.00'),
      saldos: [{ moneda: 'ARS', saldo: '-35.50' }, { moneda: 'USD', saldo: '1.00' }],
      deudas: [{ moneda: 'ARS', pendiente: '100.00' }],
    });
    await component.load();
    expect(component.netWorth()).toMatchObject({ pending: true });
    component.rate.set('100');
    expect(component.netWorth()).toMatchObject({
      currency: 'ARS', assets: 10000n, liabilities: 13550n, net: -3550n, estimated: true,
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('ARS −35,50');
    component.netCurrency.set('USD');
    expect(component.netWorth()).toMatchObject({ currency: 'USD', net: -36n });
    component.hidden.set(true);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Importes ocultos.');
    expect(fixture.nativeElement.querySelector('#net-worth-currency')).toBeNull();
  });

  it('muestra saldos, usa la referencia del espacio y respeta la privacidad', async () => {
    const { fixture, component } = await setup();
    expect(fixture.nativeElement.textContent).toContain('-35,50');
    expect(component.budgetUsage('diario')?.spent).toBeNull();
    window.dispatchEvent(new CustomEvent('gastos-reference', { detail: { space: 'other', rate: '150' } }));
    expect(component.budgetUsage('diario')?.spent).toBeNull();
    window.dispatchEvent(new CustomEvent('gastos-reference', { detail: { space: 'shared', rate: '150' } }));
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('ARS 150,00 de 100,00');
    expect(fixture.nativeElement.textContent).toContain('Límite superado');
    window.dispatchEvent(new CustomEvent('gastos-privacy', { detail: true }));
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).not.toContain('-35,50');
    expect(fixture.nativeElement.textContent).not.toContain('150,00');
    expect(fixture.nativeElement.textContent).not.toContain('Límite superado');
  });
});
