import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { Expenses, normalizeAmount, showAmount } from './expenses';
import { AuthSession } from './auth-session';
describe('Gastos', () => {
  function setup() {
    const request = vi.fn().mockResolvedValue({items:[],next_offset:null});
    TestBed.configureTestingModule({imports:[Expenses],providers:[{provide:AuthSession,useValue:{accountRequest:(...args:unknown[]) => String(args[1]).includes('expense-summary') ? Promise.resolve({fecha:'2026-11-11',mes:'2026-11',totales:[]}) : request(...args)}}]});
    const fixture=TestBed.createComponent(Expenses);
    fixture.componentRef.setInput('space','space');fixture.componentRef.setInput('account',{id:'account',nombre:'Banco'});fixture.detectChanges();
    return {fixture,request,component:fixture.componentInstance};
  }
  it('normaliza sin float ni redondeo',()=>{
    expect(normalizeAmount('0,10')).toBe('0.10');expect(normalizeAmount('999999999999.99')).toBe('999999999999.99');
    expect(showAmount('1234.50')).toBe('1.234,50');
    for(const value of ['0','-1','1.001','1e2','NaN','1.234,56','1000000000000']) expect(normalizeAmount(value)).toBeNull();
  });
  it('conserva moneda, precision e ID al reintentar',async()=>{
    const {fixture,request,component}=setup();await fixture.whenStable();
    component.description='Comida';component.currency='USD';component.amount='0,10';
    request.mockRejectedValue(new Error());await component.save();
    const payload=request.mock.calls[1][2];expect(payload.importe).toBe('0.10');expect(payload.moneda).toBe('USD');
    request.mockResolvedValue({...payload,espacio_id:'space',cuenta_id:'account'});await component.save();
    expect(request.mock.calls[2][2].id).toBe(payload.id);expect(component.items().length).toBe(1);
  });
  it('repite como gasto nuevo con fecha actual y espera la confirmación de guardado', async () => {
    const { fixture, request, component } = setup();
    await fixture.whenStable();
    const previous = {
      id: 'original', espacio_id: 'space', cuenta_id: 'account', fecha: '2020-01-01',
      descripcion: 'Café', moneda: 'USD', importe: '2.50', categoria: 'alimentos',
    };
    const today = component.date;
    request.mockClear().mockResolvedValue({ items: [previous, { ...previous, id: 'duplicate' }], next_offset: null });
    await component.load();
    expect(component.recentExpenses()).toEqual([previous]);
    fixture.detectChanges();
    fixture.nativeElement.querySelector('.recent-actions button').click();
    expect(request).toHaveBeenCalledTimes(1);
    expect(component.editing).toBeNull();
    expect(component.date).toBe(today);
    expect(component.currency).toBe('USD');
    expect(component.category).toBe('alimentos');

    request.mockImplementation(async (_method, _path, payload) => ({ ...previous, ...payload }));
    await component.save();
    expect(request.mock.calls[1]).toEqual([
      'POST', '/api/spaces/space/accounts/account/expenses',
      { id: expect.not.stringMatching(/^original$/), fecha: today, descripcion: 'Café',
        moneda: 'USD', importe: '2.50', categoria: 'alimentos' },
    ]);
  });
  it('abre el detalle cuando se pide adjuntar un comprobante al gasto guardado', async () => {
    const { fixture, request, component } = setup();
    await fixture.whenStable();
    component.description = 'Supermercado';
    component.amount = '12.50';
    request.mockImplementation(async (method, _path, payload) => method === 'POST'
      ? { ...payload, espacio_id: 'space', cuenta_id: 'account' }
      : { items: [], next_offset: null });
    await component.save();
    fixture.detectChanges();
    const details: HTMLDetailsElement = fixture.nativeElement.querySelector('.expense-details');
    expect(details.open).toBe(false);
    expect(details.querySelector('summary')?.textContent).toContain('ARS 12,50');

    component.openReceipts(component.lastSaved());
    fixture.detectChanges();
    expect(details.open).toBe(true);
    expect(details.querySelector('app-receipts')).not.toBeNull();
    fixture.destroy();
  });
  it('muestra porcentajes por moneda y abre el historial filtrado del reporte', async () => {
    const { fixture, request, component } = setup();
    await fixture.whenStable();
    request.mockResolvedValueOnce({
      desde: '2026-11-01', hasta: '2026-11-30', items: [
        { moneda: 'ARS', categoria: 'alimentos', total: '30.00' },
        { moneda: 'ARS', categoria: null, total: '10.00' },
        { moneda: 'USD', categoria: 'ocio', total: '1.00' },
      ],
    });
    await component.loadCategoryReport();
    expect(request).toHaveBeenLastCalledWith('GET', '/api/spaces/space/expense-category-summary?account=account');
    expect(component.reportGroups().map(group => group.rows.map(row => row.percent)))
      .toEqual([['75,0%', '25,0%'], ['100,0%']]);
    fixture.detectChanges();
    const panel: HTMLElement = fixture.nativeElement.querySelector('.category-report');
    expect(panel.textContent).toContain('75,0%');
    window.dispatchEvent(new CustomEvent('gastos-privacy', { detail: true }));
    fixture.detectChanges();
    expect(panel.textContent).not.toContain('75,0%');
    window.dispatchEvent(new CustomEvent('gastos-privacy', { detail: false }));

    component.filterText = 'otro filtro';
    await component.viewCategoryExpenses(component.reportGroups()[0].rows[1]);
    expect(request).toHaveBeenLastCalledWith(
      'GET', '/api/spaces/space/accounts/account/expenses?offset=0&desde=2026-11-01&hasta=2026-11-30&categoria=sin_categoria&moneda=ARS',
    );
  });
  it('no actualiza otra cuenta tras destruir el formulario',async()=>{
    const {fixture,request,component}=setup();await fixture.whenStable();
    let finish!: (value:unknown)=>void;request.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
    component.description='Comida';component.amount='10';const pending=component.save();fixture.destroy();
    finish({id:'one',fecha:'2026-11-06',importe:'10.00',moneda:'ARS'});await pending;expect(component.items()).toEqual([]);
  });
});
