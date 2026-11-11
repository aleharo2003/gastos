import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { ExpenseTotals } from './expense-totals';
import { AuthSession } from './auth-session';
describe('Totales visibles y privados',()=>{
  afterEach(()=>localStorage.clear());
  async function setup(){
    const request=vi.fn().mockResolvedValue({fecha:'2026-11-11',mes:'2026-11',totales:[{moneda:'USD',dia:'123.45',mes:'678.90'}]});
    TestBed.configureTestingModule({imports:[ExpenseTotals],providers:[{provide:AuthSession,useValue:{accountRequest:request}}]});
    const f=TestBed.createComponent(ExpenseTotals);f.componentRef.setInput('space','s');f.detectChanges();await f.whenStable();f.detectChanges();
    return {f,c:f.componentInstance,request};
  }
  it('oculta importes y desglose, y conserva la preferencia',async()=>{
    const {f,c}=await setup();expect(f.nativeElement.textContent).toContain('123,45');
    c.toggle();f.detectChanges();
    expect(f.nativeElement.textContent).not.toContain('123,45');expect(f.nativeElement.textContent).not.toContain('678,90');
    expect(f.nativeElement.querySelector('details')).toBeNull();expect(localStorage.getItem('gastos.totals.hidden')).toBe('true');
  });
  it('no convierte una falla en un total cero',async()=>{
    const {f,c,request}=await setup();request.mockRejectedValue(new Error());await c.load();f.detectChanges();
    expect(c.data()).toBeNull();expect(c.total('dia')).toBe('—');expect(f.nativeElement.textContent).toContain('No pudimos calcular');
  });
  it('ignora un resumen tardio de otra cuenta',async()=>{
    const {c,request}=await setup();let finish!:(v:unknown)=>void;
    request.mockImplementationOnce(()=>new Promise(resolve=>finish=resolve));const old=c.load();
    c.account='new';await c.load();finish({fecha:'2026-11-11',mes:'2026-11',totales:[{moneda:'USD',dia:'999.00',mes:'999.00'}]});await old;
    expect(c.total('dia')).toBe('USD 123,45');
  });
});
