import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { Accounts } from './accounts';
import { AuthSession } from './auth-session';

describe('Cuentas', () => {
  function setup(balance = vi.fn().mockResolvedValue({ totales: [] })) {
    const request = vi.fn().mockResolvedValue({ items: [], next_offset: null });
    TestBed.configureTestingModule({ imports:[Accounts], providers:[{provide:AuthSession,useValue:{accountRequest:(...args:unknown[]) => String(args[1]).endsWith('/due-overview') ? Promise.resolve({fecha:'2026-11-17',fin_semana:'2026-11-22',grupos:{hoy:{cantidad:0,totales:[],items:[]},semana:{cantidad:0,totales:[],items:[]},vencidas:{cantidad:0,totales:[],items:[]}},resumen_mes:[],saldos:[],presupuesto:{limites:{diario:null,semanal:null},gastos:[]}}) : String(args[1]).includes('/installment-drafts?') ? Promise.resolve({borradores:0,items:[],next_offset:null}) : String(args[1]).includes('/installments?month=') ? Promise.resolve({mes:new URL('https://local'+String(args[1])).searchParams.get('month'),totales:[],items:[],next_offset:null}) : String(args[1]).includes('account-balance') ? balance(...args) : (String(args[1]).includes('/incomes') || String(args[1]).includes('/transfers') || String(args[1]).includes('/savings-goals') || String(args[1]).includes('/commitments')) ? Promise.resolve({items:[],next_offset:null}) : String(args[1]).includes('spending-plan') ? Promise.resolve({version:0,datos:{limites:{diario:null,semanal:null},conceptos:[]}}) : String(args[1]).includes('expense-summary') ? Promise.resolve({fecha:'2026-11-11',mes:'2026-11',totales:[]}) : String(args[1]).includes('/expenses') ? Promise.resolve({items:[],next_offset:null}) : request(...args)}}] });
    const fixture = TestBed.createComponent(Accounts);
    fixture.componentRef.setInput('space','space-1'); fixture.detectChanges();
    return { fixture, request, component:fixture.componentInstance };
  }
  it('muestra estado vacio y permite crear cuenta', async () => {
    const {fixture, request, component} = setup(); await fixture.whenStable(); fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Todavía no tenés cuentas');
    request.mockResolvedValue({id:'one',espacio_id:'space-1',nombre:'Efectivo'});
    component.name='Efectivo'; await component.save(); fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Efectivo');
    expect(component.name).toBe('');
  });
  it('consolida los saldos del espacio con la referencia y oculta el total', async () => {
    const balance = vi.fn().mockResolvedValue({ totales: [
      { moneda: 'ARS', ingresos: '0.00', gastos: '50.00', saldo: '-50.00' },
      { moneda: 'USD', ingresos: '1.00', gastos: '0.00', saldo: '1.00' },
      { moneda: 'EUR', ingresos: '0.00', gastos: '0.00', saldo: '0.00' },
    ] });
    const { fixture, component } = setup(balance);
    await fixture.whenStable();
    component.tab.set('accounts');
    fixture.detectChanges();
    await fixture.whenStable();
    expect(balance).toHaveBeenCalledWith('GET', '/api/spaces/space-1/account-balance');
    expect(component.consolidatedBalance()?.value).toBeNull();

    component.referenceRate.set('100');
    expect(component.consolidatedBalance()).toEqual({ value: 5000n, estimated: true });
    component.balanceCurrency.set('USD');
    expect(component.consolidatedBalance()?.value).toBe(50n);
    component.amountsHidden.set(true);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('#account-total-currency')).toBeNull();
  });

  it('consulta solo el saldo de la cuenta abierta y respeta la privacidad', async () => {
    const balance = vi.fn().mockImplementation(async (_method, path: string) => ({
      totales: path.endsWith('?account=one') ? [
        { moneda: 'ARS', ingresos: '1250.50', gastos: '0.00', saldo: '1250.50' },
        { moneda: 'USD', ingresos: '20.00', gastos: '0.00', saldo: '20.00' },
      ] : [],
    }));
    const { fixture, component, request } = setup(balance);
    await fixture.whenStable();
    request.mockResolvedValue({ items: [
      { id: 'one', espacio_id: 'space-1', nombre: 'Banco' },
      { id: 'two', espacio_id: 'space-1', nombre: 'Efectivo' },
    ], next_offset: null });
    await component.load();
    component.tab.set('accounts');
    fixture.detectChanges();
    await fixture.whenStable();
    balance.mockClear();

    fixture.nativeElement.querySelector('button[aria-label="Ver saldo de Banco"]').click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(balance.mock.calls).toEqual([['GET', '/api/spaces/space-1/account-balance?account=one']]);
    const panel: HTMLElement = fixture.nativeElement.querySelector('#account-balance-one');
    expect(panel.textContent).toContain('1.250,50');
    expect(panel.textContent).toContain('20,00');
    expect(fixture.nativeElement.querySelector('#account-balance-two').hidden).toBe(true);

    window.dispatchEvent(new CustomEvent('gastos-privacy', { detail: true }));
    fixture.detectChanges();
    expect(panel.textContent).toContain('••••');
    expect(panel.textContent).not.toContain('1.250,50');
    window.dispatchEvent(new CustomEvent('gastos-privacy', { detail: false }));
  });
  it('actualiza el nombre conservando el ID y los datos de la cuenta seleccionada', async () => {
    const { fixture, request, component } = setup();
    await fixture.whenStable();
    const current = { id: 'one', espacio_id: 'space-1', nombre: 'Efectivo' };
    component.items.set([current]);
    component.selected.set([current]);
    component.editAccount(current);
    component.editedName = ' Caja ';
    const updated = { ...current, nombre: 'Caja' };
    request.mockResolvedValueOnce(updated);
    await component.renameAccount();

    expect(request).toHaveBeenCalledWith('PATCH', '/api/spaces/space-1/accounts/one',
      { nombre: 'Caja', nombre_anterior: 'Efectivo' });
    expect(component.items()).toEqual([updated]);
    expect(component.selected()).toEqual([updated]);
    expect(component.editingAccount()).toBeNull();
  });

  it('conserva ID ante respuesta perdida y evita doble envio', async () => {
    const {fixture,request,component}=setup(); await fixture.whenStable();
    request.mockRejectedValue(new Error()); component.name='Banco';
    await component.save();
    const first=request.mock.calls[1][2].id;
    request.mockResolvedValue({id:first,espacio_id:'space-1',nombre:'Banco'});
    await component.save();
    expect(request.mock.calls[2][2].id).toBe(first);
    expect(component.items().length).toBe(1);
  });
  it('ignora una respuesta despues de destruir la pantalla', async () => {
    const {fixture,request,component}=setup(); await fixture.whenStable();
    let finish!: (value:unknown)=>void;
    request.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
    component.name='Banco'; const pending=component.save();
    fixture.destroy(); finish({id:'one',espacio_id:'space-1',nombre:'Banco'}); await pending;
    expect(component.items()).toEqual([]);
  });
});
