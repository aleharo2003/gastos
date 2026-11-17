import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { Incomes } from './incomes';
import { AuthSession } from './auth-session';
describe('Ingresos por cuenta',()=>{
  afterEach(()=>{localStorage.clear();});
  async function setup(account='bank'){
    const request=vi.fn().mockImplementation(async(method,path,body)=>path.includes('account-balance')
      ?{totales:[{moneda:'ARS',ingresos:'100.10',gastos:'200.00',saldo:'-99.90'}]}
      :method==='POST'?{...body,espacio_id:'s',cuenta_id:'bank'}:{items:[],next_offset:null});
    TestBed.configureTestingModule({imports:[Incomes],providers:[{provide:AuthSession,useValue:{accountRequest:request}}]});
    const f=TestBed.createComponent(Incomes);
    f.componentRef.setInput('space','s');f.componentRef.setInput('account',{id:account,nombre:account?'Banco':'Todas las cuentas'});
    f.componentRef.setInput('accounts',[{id:'bank',nombre:'Banco'}]);f.detectChanges();await f.whenStable();f.detectChanges();
    return {f,c:f.componentInstance,request};
  }
  it('conserva destino, decimales e identificador al reintentar',async()=>{
    const {c,request}=await setup();c.description='Sueldo';c.amount='100,10';
    request.mockRejectedValue(new Error());await c.save();await c.save();
    const writes=request.mock.calls.filter(row=>row[0]==='POST');
    expect(writes).toHaveLength(2);expect(writes[0][1]).toBe('/api/spaces/s/accounts/bank/incomes');
    expect(writes[0][2]).toEqual(writes[1][2]);expect(writes[0][2].importe).toBe('100.10');
    expect(c.description).toBe('Sueldo');expect(c.hasPendingWork()).toBe(true);
  });
  it('exige cuenta desde la vista global y actualiza saldo tras guardar',async()=>{
    const {c,request}=await setup('');c.description='Regalo';c.amount='10';
    await c.save();expect(request.mock.calls.some(row=>row[0]==='POST')).toBe(false);
    c.createAccount='bank';await c.save();
    expect(request.mock.calls.filter(row=>row[0]==='POST')).toHaveLength(1);
    expect(c.description).toBe('');expect(c.notice()).toContain('registrado');
    expect(request.mock.calls.filter(row=>String(row[1]).includes('account-balance')).length).toBeGreaterThan(1);
  });
  it('muestra saldo negativo y respeta el ojo de privacidad',async()=>{
    const {f}=await setup();expect(f.nativeElement.textContent).toContain('-99,90');
    window.dispatchEvent(new CustomEvent('gastos-privacy',{detail:true}));f.detectChanges();
    expect(f.nativeElement.textContent).not.toContain('-99,90');
    expect(f.nativeElement.textContent).not.toContain('100,10');
  });
  it('no deja que una respuesta vieja reemplace el saldo actualizado',async()=>{
    const {c,request}=await setup();
    let finish!:(value:unknown)=>void;request.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
    const first=c.loadBalance();
    request.mockResolvedValue({totales:[{moneda:'ARS',ingresos:'5.00',gastos:'0.00',saldo:'5.00'}]});
    await c.loadBalance();finish({totales:[]});await first;
    expect(c.balance()!.totales[0].saldo).toBe('5.00');
  });
  it('descarta respuestas de guardado al destruir la pantalla',async()=>{
    const {f,c,request}=await setup();let finish!:(value:unknown)=>void;
    request.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
    c.description='Sueldo';c.amount='1';const pending=c.save();f.destroy();finish({});await pending;
    expect(c.notice()).toBe('');
  });
});
