import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { Expenses } from './expenses';
import { AuthSession } from './auth-session';

describe('Sugerencias de categoria',()=>{
  const suggestion={categoria:'alimentos',coincidencias:2,total:2};
  async function setup(){
    const request=vi.fn().mockResolvedValue({items:[],next_offset:null});
    TestBed.configureTestingModule({imports:[Expenses],providers:[{provide:AuthSession,useValue:{accountRequest:(...args:unknown[]) => String(args[1]).includes('expense-summary') ? Promise.resolve({fecha:'2026-11-11',mes:'2026-11',totales:[]}) : request(...args)}}]});
    const fixture=TestBed.createComponent(Expenses);
    fixture.componentRef.setInput('space','space');fixture.componentRef.setInput('account',{id:'account',nombre:'Banco'});
    fixture.detectChanges();await fixture.whenStable();
    return {request,fixture,c:fixture.componentInstance};
  }
  it('muestra propuesta sin seleccionar hasta la confirmacion',async()=>{
    const {request,fixture,c}=await setup();c.description='Cerveza';request.mockResolvedValue(suggestion);await c.requestSuggestion();fixture.detectChanges();
    expect(c.category).toBe('');expect(fixture.nativeElement.textContent).toContain('Usar Alimentos');
    expect(request.mock.calls.at(-1)![1]).toContain('category-suggestion?descripcion=Cerveza');
    c.applySuggestion();expect(c.category).toBe('alimentos');expect(request).toHaveBeenCalledTimes(2);
  });
  it('descarta respuesta vieja cuando la descripcion cambio',async()=>{
    const {request,c}=await setup();let finish!:(value:unknown)=>void;
    request.mockImplementation(()=>new Promise(resolve=>finish=resolve));c.description='Cerveza';const pending=c.requestSuggestion();
    c.description='Seguro auto';c.clearSuggestion();finish(suggestion);await pending;expect(c.suggestion()).toBeNull();
  });
  it('no pisa una categoria elegida mientras espera',async()=>{
    const {request,c}=await setup();let finish!:(value:unknown)=>void;
    request.mockImplementation(()=>new Promise(resolve=>finish=resolve));c.description='Cerveza';const pending=c.requestSuggestion();
    c.category='ocio';c.clearSuggestion();finish(suggestion);await pending;expect(c.category).toBe('ocio');expect(c.suggestion()).toBeNull();
  });
  it('permite guardar aunque falle la sugerencia',async()=>{
    const {request,c}=await setup();c.description='Cerveza';c.amount='10';request.mockRejectedValue(new Error());await c.requestSuggestion();
    expect(c.error()).toBe('');expect(c.suggestionNote()).toContain('guardar igual');
    request.mockImplementation(async(_method,_path,payload)=>({...payload,espacio_id:'space',cuenta_id:'account'}));await c.save();
    expect(c.items()).toHaveLength(1);expect(c.notice()).toBe('Gasto guardado.');
  });
  it('descarta respuesta tras destruir y omite consultas con categoria',async()=>{
    const {request,fixture,c}=await setup();c.description='Cerveza';c.category='ocio';await c.requestSuggestion();expect(request).toHaveBeenCalledTimes(1);
    c.category='';let finish!:(value:unknown)=>void;request.mockImplementation(()=>new Promise(resolve=>finish=resolve));
    const pending=c.requestSuggestion();fixture.destroy();finish(suggestion);await pending;expect(c.suggestion()).toBeNull();
  });
  it('no deja que una respuesta anterior reemplace una nueva',async()=>{
    const {request,c}=await setup();let finish!:(value:unknown)=>void;request.mockImplementationOnce(()=>new Promise(resolve=>finish=resolve));
    c.description='Cerveza';const pending=c.requestSuggestion();c.description='Seguro auto';c.clearSuggestion();
    request.mockResolvedValue({categoria:'auto',coincidencias:3,total:3});await c.requestSuggestion();finish(suggestion);await pending;
    expect(c.suggestion()?.categoria).toBe('auto');expect(c.category).toBe('');
  });
});
