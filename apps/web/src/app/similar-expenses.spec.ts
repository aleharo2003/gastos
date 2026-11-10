import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { SimilarExpenses } from './similar-expenses';
import { AuthSession } from './auth-session';

describe('Gastos similares',()=>{
  const row={id:'other',descripcion:'Cerveza',fecha:'2026-11-10',moneda:'USD',importe:'12.50',categoria:'alimentos',coincidencia_aproximada:true};
  function setup(request=vi.fn().mockResolvedValue({referencia_id:'source',items:[row]})){
    TestBed.configureTestingModule({imports:[SimilarExpenses],providers:[{provide:AuthSession,useValue:{accountRequest:request}}]});
    const fixture=TestBed.createComponent(SimilarExpenses);fixture.componentRef.setInput('path','/api/spaces/space/accounts/account/expenses/source/similar');
    fixture.componentRef.setInput('categories',[{id:'alimentos',label:'Alimentos'}]);fixture.detectChanges();
    return {request,fixture,c:fixture.componentInstance};
  }
  it('consulta bajo demanda y presenta moneda, fecha y parecido sin modificar datos',async()=>{
    const {request,fixture}=setup();await fixture.whenStable();fixture.detectChanges();
    const text=fixture.nativeElement.textContent;expect(text).toContain('USD 12,50');expect(text).toContain('10/11/2026');expect(text).toContain('Alimentos');expect(text).toContain('Descripción parecida');
    expect(request).toHaveBeenCalledTimes(1);expect(request.mock.calls[0][0]).toBe('GET');
  });
  it('permite reintentar una consulta fallida',async()=>{
    const {request,fixture,c}=setup(vi.fn().mockRejectedValue(new Error()));await fixture.whenStable();expect(c.error()).toContain('volver a intentar');
    request.mockResolvedValue({referencia_id:'source',items:[]});await c.load();fixture.detectChanges();expect(c.error()).toBe('');expect(fixture.nativeElement.textContent).toContain('No encontramos otros gastos');
  });
  it('descarta respuestas al cerrar el panel y evita consultas simultaneas',async()=>{
    let finish!:(value:unknown)=>void;const request=vi.fn().mockImplementation(()=>new Promise(resolve=>finish=resolve));
    const {fixture,c}=setup(request);await c.load();expect(request).toHaveBeenCalledTimes(1);fixture.destroy();finish({referencia_id:'source',items:[row]});
    await Promise.resolve();await Promise.resolve();expect(c.items()).toEqual([]);
  });
});
