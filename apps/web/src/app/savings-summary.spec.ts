import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { AuthSession } from './auth-session';
import { SavingsSummary } from './savings-summary';

describe('Resumen de ahorros', () => {
  afterEach(() => localStorage.clear());

  it('separa el resultado de los saldos y convierte la referencia sin perder el signo', async () => {
    localStorage.setItem('gastos.reference.shared', JSON.stringify({ rate: '1700', date: '2026-11-24' }));
    const accountRequest = vi.fn().mockImplementation(async (_method: string, path: string) => {
      const mes = new URL(path, 'https://example.test').searchParams.get('month');
      return {
        mes, hasta: mes + '-20', fecha_saldos: mes + '-20', next_offset: null,
        ingresos: [
          { concepto: 'Sueldo', moneda: 'USD', total: '50.00' },
          { concepto: 'Sueldo', moneda: 'ARS', total: '1700.00' },
        ],
        actividad: [
          { tipo: 'cuotas', moneda: 'ARS', total: '3400.00' },
          { tipo: 'otros_gastos', moneda: 'USD', total: '60.00' },
          { tipo: 'ingresos_anuales', moneda: 'USD', total: '150.00' },
        ],
        cuentas: [{ id: 'bank', nombre: 'Banco', activa: true, saldos: [{ moneda: 'USD', total: '81.00' }] }],
        saldo_total: [{ moneda: 'USD', total: '81.00' }],
      };
    });
    TestBed.configureTestingModule({
      imports: [SavingsSummary], providers: [{ provide: AuthSession, useValue: { accountRequest } }],
    });
    const fixture = TestBed.createComponent(SavingsSummary);
    fixture.componentRef.setInput('space', 'shared');
    fixture.detectChanges();
    await fixture.whenStable();
    const component = fixture.componentInstance;
    const rows = component.monthRows()!;
    expect(rows.net.USD).toBe(-1000n);
    expect(rows.net.ARS).toBe(-170000n);
    component.equivalents.set(true);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.month-net').textContent).toContain('−18.700,00');
    expect(fixture.nativeElement.querySelector('tfoot').textContent).toContain('137.700,00');
    expect(fixture.nativeElement.textContent).toContain('24/11/2026');
    window.dispatchEvent(new CustomEvent('gastos-privacy', { detail: true }));
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('table')).toBeNull();
  });
});
