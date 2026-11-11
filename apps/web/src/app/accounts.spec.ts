import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { Accounts } from './accounts';
import { AuthSession } from './auth-session';

describe('Cuentas', () => {
  function setup() {
    const request = vi.fn().mockResolvedValue({ items: [], next_offset: null });
    TestBed.configureTestingModule({ imports:[Accounts], providers:[{provide:AuthSession,useValue:{accountRequest:(...args:unknown[]) => String(args[1]).includes('expense-summary') ? Promise.resolve({fecha:'2026-11-11',mes:'2026-11',totales:[]}) : String(args[1]).includes('/expenses') ? Promise.resolve({items:[],next_offset:null}) : request(...args)}}] });
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
