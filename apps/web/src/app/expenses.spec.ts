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
  it('no actualiza otra cuenta tras destruir el formulario',async()=>{
    const {fixture,request,component}=setup();await fixture.whenStable();
    let finish!: (value:unknown)=>void;request.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
    component.description='Comida';component.amount='10';const pending=component.save();fixture.destroy();
    finish({id:'one',fecha:'2026-11-06',importe:'10.00',moneda:'ARS'});await pending;expect(component.items()).toEqual([]);
  });
});
