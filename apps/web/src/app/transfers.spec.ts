import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { Transfers } from './transfers';
import { AuthSession } from './auth-session';
describe('Ahorros y transferencias',()=>{
  afterEach(()=>{localStorage.clear();});
  async function setup(){
    const request=vi.fn().mockImplementation(async(method,path,body)=>method==='POST'?{...body,espacio_id:'s'}:{items:[],next_offset:null});
    TestBed.configureTestingModule({imports:[Transfers],providers:[{provide:AuthSession,useValue:{accountRequest:request}}]});
    const f=TestBed.createComponent(Transfers);f.componentRef.setInput('space','s');
    f.componentRef.setInput('accounts',[{id:'bank',nombre:'Banco'},{id:'savings',nombre:'Ahorros'}]);f.detectChanges();await f.whenStable();f.detectChanges();
    return {f,c:f.componentInstance,request};
  }
  it('exige dos cuentas distintas y excluye origen del destino',async()=>{
    const {c,request}=await setup();c.origin='bank';c.destination='bank';c.amount='10';c.description='Ahorro';
    await c.save();expect(request.mock.calls.some(row=>row[0]==='POST')).toBe(false);
    expect(c.destinations().map(row=>row.id)).toEqual(['savings']);c.originChanged();expect(c.destination).toBe('');
  });
  it('conserva UUID, cuentas y precision cuando se pierde la respuesta',async()=>{
    const {c,request}=await setup();c.origin='bank';c.destination='savings';c.description='Ahorro del mes';c.amount='100,10';
    request.mockRejectedValue(new Error());await c.save();await c.save();
    const writes=request.mock.calls.filter(row=>row[0]==='POST');
    expect(writes).toHaveLength(2);expect(writes[0][2]).toEqual(writes[1][2]);
    expect(writes[0][2]).toMatchObject({origen_id:'bank',destino_id:'savings',importe:'100.10',moneda:'ARS'});
    expect(c.amount).toBe('100,10');
  });
  it('permite retirar ahorros y avisa al contenedor para actualizar saldos',async()=>{
    const {c,request}=await setup();const changed=vi.fn();c.changed.subscribe(changed);
    c.origin='savings';c.destination='bank';c.amount='10';c.description='Retiro';await c.save();
    expect(request.mock.calls.find(row=>row[0]==='POST')![2]).toMatchObject({origen_id:'savings',destino_id:'bank'});
    expect(changed).toHaveBeenCalledOnce();expect(c.amount).toBe('');expect(c.notice()).toContain('ambas cuentas');
  });
  it('filtra por cuenta antes de paginar y oculta importes con el ojo',async()=>{
    const {f,c,request}=await setup();
    const row={id:'one',espacio_id:'s',origen_id:'bank',destino_id:'savings',descripcion:'Ahorro',fecha:'2026-11-17',moneda:'ARS',importe:'100.00'};
    request.mockResolvedValue({items:[row],next_offset:100});c.historyAccount='savings';await c.applyHistory();
    request.mockResolvedValue({items:[],next_offset:null});await c.load(true);
    expect(request.mock.calls.at(-1)![1]).toContain('offset=100&account=savings');
    f.detectChanges();expect(f.nativeElement.textContent).toContain('100,00');
    window.dispatchEvent(new CustomEvent('gastos-privacy',{detail:true}));f.detectChanges();
    expect(f.nativeElement.textContent).not.toContain('100,00');
  });
  it('ignora respuestas tras destruir el formulario',async()=>{
    const {f,c,request}=await setup();let finish!:(value:unknown)=>void;
    request.mockImplementation((_m,_p,body)=>new Promise(resolve=>{finish=()=>resolve({...body,espacio_id:'s'});}));
    c.origin='bank';c.destination='savings';c.description='Ahorro';c.amount='1';
    const task=c.save();f.destroy();finish({});await task;expect(c.notice()).toBe('');
  });
});
