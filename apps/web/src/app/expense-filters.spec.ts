import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { Expenses } from './expenses';
import { AuthSession } from './auth-session';

describe('Filtros y categorías',()=>{
  const row={id:'expense',espacio_id:'space',cuenta_id:'account',fecha:'2026-11-06',descripcion:'Cerveza',moneda:'ARS',importe:'10.00',categoria:'alimentos'};
  async function setup(){
    const request=vi.fn().mockResolvedValue({items:[row],next_offset:100});
    TestBed.configureTestingModule({imports:[Expenses],providers:[{provide:AuthSession,useValue:{accountRequest:request}}]});
    const fixture=TestBed.createComponent(Expenses);
    fixture.componentRef.setInput('space','space');fixture.componentRef.setInput('account',{id:'account',nombre:'Banco'});
    fixture.detectChanges();await fixture.whenStable();
    return {request,c:fixture.componentInstance};
  }
  it('mantiene filtros aplicados al paginar aunque cambie el borrador',async()=>{
    const {request,c}=await setup();c.filterText='10% & cerveza';c.filterFrom='2026-11-01';c.filterCategory='alimentos';
    await c.applyFilters();c.filterText='otro';await c.load(true);
    const url=new URL(request.mock.calls.at(-1)![1],'https://local.test');
    expect(url.searchParams.get('texto')).toBe('10% & cerveza');expect(url.searchParams.get('offset')).toBe('100');
    expect(url.searchParams.get('categoria')).toBe('alimentos');
    await c.applyFilters(true);expect(request.mock.calls.at(-1)![1]).toMatch(/\?offset=0$/);
  });
  it('rechaza rango invertido sin perder la lista',async()=>{
    const {request,c}=await setup();c.filterFrom='2026-12-01';c.filterTo='2026-11-01';await c.applyFilters();
    expect(request).toHaveBeenCalledTimes(1);expect(c.items()).toHaveLength(1);expect(c.error()).toContain('Desde');
  });
  it('envia categoria al editar y recarga resultados filtrados sin perder acceso al comprobante',async()=>{
    const {request,c}=await setup();c.filterCategory='alimentos';await c.applyFilters();c.edit(row);c.category='ocio';
    request.mockResolvedValueOnce({...row,categoria:'ocio'}).mockResolvedValueOnce({items:[],next_offset:null});
    await c.save();
    const payload=request.mock.calls.find(call=>call[0]==='PATCH')![2];
    expect(payload.original.categoria).toBe('alimentos');expect(payload.nuevo.categoria).toBe('ocio');
    expect(c.items()).toEqual([]);expect(c.lastSaved()).toBe(row.id);c.openReceipts(row.id);expect(c.receiptOutsideList()).toBe(true);
  });
});
