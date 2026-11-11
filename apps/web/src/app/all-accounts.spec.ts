import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { Expenses } from './expenses';
import { AuthSession } from './auth-session';
describe('Operaciones desde Todas las cuentas',()=>{
  async function setup(){
    const rows=[{id:'one',cuenta_id:'bank',espacio_id:'s',fecha:'2026-11-11',descripcion:'Comida',moneda:'ARS',importe:'10.00'},
      {id:'two',cuenta_id:'cash',espacio_id:'s',fecha:'2026-11-11',descripcion:'Pan',moneda:'ARS',importe:'1.00'}];
    const request=vi.fn().mockImplementation(async(method,path,body)=>{
      if(path.includes('expense-summary')) return {fecha:'2026-11-11',mes:'2026-11',totales:[]};
      if(method==='PATCH')return {...rows[0],...body.nuevo};
      if(method==='POST')return {...body,espacio_id:'s',cuenta_id:'cash'};
      return {items:rows,next_offset:null};
    });
    TestBed.configureTestingModule({imports:[Expenses],providers:[{provide:AuthSession,useValue:{accountRequest:request}}]});
    const f=TestBed.createComponent(Expenses);f.componentRef.setInput('space','s');f.componentRef.setInput('account',{id:'',nombre:'Todas las cuentas'});
    f.detectChanges();await f.whenStable();return {c:f.componentInstance,request,rows};
  }
  it('edita y consulta comprobantes en la cuenta original de cada fila',async()=>{
    const {c,request,rows}=await setup();
    expect(request.mock.calls[0][1]).toBe('/api/spaces/s/expenses?offset=0');
    expect(c.receiptPath('two')).toBe('/api/spaces/s/accounts/cash/expenses/two/receipts');
    expect(c.similarPath('one')).toBe('/api/spaces/s/accounts/bank/expenses/one/similar');
    c.edit(rows[0]);c.date='2026-11-10';await c.save();
    expect(request.mock.calls.find(row=>row[0]==='PATCH')![1]).toBe('/api/spaces/s/accounts/bank/expenses/one');
  });
  it('exige cuenta al crear y conserva el destino del comprobante fuera de la lista',async()=>{
    const {c,request}=await setup();c.description='Compra';c.amount='10';await c.save();
    expect(c.error()).toContain('Elegí la cuenta');expect(request.mock.calls.some(row=>row[0]==='POST')).toBe(false);
    c.createAccount='cash';await c.save();
    expect(request.mock.calls.find(row=>row[0]==='POST')![1]).toBe('/api/spaces/s/accounts/cash/expenses');
    const id=c.lastSaved()!;c.items.set([]);
    expect(c.receiptPath(id)).toBe(`/api/spaces/s/accounts/cash/expenses/${id}/receipts`);
  });
});
