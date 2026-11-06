import { TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { vi } from 'vitest';
import { Expenses } from './expenses';
import { AuthSession } from './auth-session';

describe('Edicion de gastos',()=>{
  const row={id:'expense',espacio_id:'space',cuenta_id:'account',fecha:'2026-11-06',descripcion:'Comida',moneda:'ARS',importe:'10.00'};
  async function setup(){
    const request=vi.fn().mockResolvedValue({items:[row],next_offset:null});
    TestBed.configureTestingModule({imports:[Expenses],providers:[{provide:AuthSession,useValue:{accountRequest:request}}]});
    const fixture=TestBed.createComponent(Expenses);
    fixture.componentRef.setInput('space','space');fixture.componentRef.setInput('account',{id:'account',nombre:'Banco'});
    fixture.detectChanges();await fixture.whenStable();
    return {request,component:fixture.componentInstance};
  }
  it('edita conservando identificador y original sin duplicar filas',async()=>{
    const {request,component}=await setup();component.edit(row);component.date='2026-11-01';
    request.mockResolvedValue({...row,fecha:component.date});await component.save();
    const [method,path,body]=request.mock.calls[1];
    expect(method).toBe('PATCH');expect(path).toContain('/expense');expect(body.original.fecha).toBe('2026-11-06');expect(body.nuevo.id).toBe(row.id);
    expect(component.items()).toHaveLength(1);expect(component.items()[0].fecha).toBe('2026-11-01');expect(component.editing).toBeNull();
  });
  it('conserva cambios locales ante conflicto sin reintento automatico',async()=>{
    const {request,component}=await setup();component.edit(row);component.amount='25';
    request.mockRejectedValue(new HttpErrorResponse({status:409}));await component.save();
    expect(component.amount).toBe('25');expect(component.editing?.importe).toBe('10.00');expect(component.error()).toContain('otra sesión');expect(request).toHaveBeenCalledTimes(2);
  });
});
