import { TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { vi } from 'vitest';
import { SavingsGoals,type Goal } from './savings-goals';
import { AuthSession } from './auth-session';
describe('Metas de ahorro',()=>{
  afterEach(()=>{localStorage.clear();vi.restoreAllMocks();});
  async function setup(){
    const goal:Goal={id:'goal',espacio_id:'s',cuenta_id:'savings',cuenta_nombre:'Ahorros',nombre:'Vacaciones',moneda:'ARS',objetivo:'100.00',
      fecha_objetivo:null,archivada:false,version:0,saldo:'25.00',acumulado:'25.00',faltante:'75.00',porcentaje:'25.0',alcanzada:false,vencida:false};
    const request=vi.fn().mockImplementation(async(method,path,body)=>method==='GET'?{items:[goal],next_offset:null}:{...goal,...body});
    TestBed.configureTestingModule({imports:[SavingsGoals],providers:[{provide:AuthSession,useValue:{accountRequest:request}}]});
    const fixture=TestBed.createComponent(SavingsGoals);fixture.componentRef.setInput('space','s');fixture.componentRef.setInput('accounts',[{id:'savings',nombre:'Ahorros'}]);
    fixture.detectChanges();await fixture.whenStable();fixture.detectChanges();
    return {f:fixture,c:fixture.componentInstance,request,goal};
  }
  it('muestra objetivo, faltante y progreso y respeta privacidad',async()=>{
    const {f}=await setup();expect(f.nativeElement.textContent).toContain('75,00');expect(f.nativeElement.querySelector('progress').value).toBe(25);
    window.dispatchEvent(new CustomEvent('gastos-privacy',{detail:true}));f.detectChanges();
    expect(f.nativeElement.textContent).not.toContain('75,00');expect(f.nativeElement.querySelector('progress')).toBeNull();expect(f.nativeElement.querySelector('form')).toBeNull();
  });
  it('conserva UUID y dinero exacto al reintentar la creacion',async()=>{
    const {c,request}=await setup();c.name='Casa';c.account='savings';c.target='123,45';
    request.mockRejectedValue(new Error());await c.save();await c.save();
    const writes=request.mock.calls.filter(call=>call[0]==='POST');expect(writes).toHaveLength(2);
    expect(writes[0][2]).toEqual(writes[1][2]);expect(writes[0][2].objetivo).toBe('123.45');expect(c.name).toBe('Casa');
  });
  it('edita y archiva conservando cuenta y moneda y el borrador ante conflicto',async()=>{
    const {c,request,goal}=await setup();c.edit(goal);c.name='Viaje';c.archived=true;
    request.mockRejectedValue(new HttpErrorResponse({status:409}));await c.save();
    const write=request.mock.calls.find(call=>call[0]==='PATCH')!;
    expect(write[1]).toBe('/api/spaces/s/savings-goals/goal');
    expect(write[2]).toEqual({nombre:'Viaje',objetivo:'100.00',fecha_objetivo:null,version:0,archivada:true});
    expect(c.name).toBe('Viaje');expect(c.error()).toContain('borrador');
  });
  it('prepara aportes y retiros sin guardar ni modificar saldos',async()=>{
    const {c,request,goal}=await setup();const prepare=vi.fn();c.prepareTransfer.subscribe(prepare);
    c.prepare(goal);c.prepare(goal,true);
    expect(prepare.mock.calls[0][0]).toMatchObject({cuenta_id:'savings',moneda:'ARS',retirar:false});
    expect(prepare.mock.calls[1][0].retirar).toBe(true);
    expect(request.mock.calls.every(call=>call[0]==='GET')).toBe(true);
  });
  it('actualiza progreso por revision sin perder el borrador',async()=>{
    const {f,c,request,goal}=await setup();c.name='Pendiente';c.target='200';
    request.mockResolvedValue({items:[{...goal,saldo:'50.00',acumulado:'50.00',faltante:'50.00',porcentaje:'50.0'}],next_offset:null});
    f.componentRef.setInput('revision',1);f.detectChanges();await f.whenStable();
    expect(c.items()[0].porcentaje).toBe('50.0');expect(c.name).toBe('Pendiente');
  });
  it('ignora respuestas de otra pantalla y pagina con el filtro guardado',async()=>{
    const {f,c,request}=await setup();c.includeArchived=true;await c.applyArchived();c.next.set(100);await c.load(true);
    expect(request.mock.calls.at(-1)![1]).toContain('offset=100&archived=true');
    let finish!:(value:unknown)=>void;request.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
    c.name='Casa';c.target='100';c.account='savings';const saving=c.save();f.destroy();finish({});await saving;
    expect(c.notice()).toBe('');
  });
});
