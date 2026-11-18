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
});
