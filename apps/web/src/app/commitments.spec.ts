import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { Commitments,type Commitment,type Installment } from './commitments';
import { AuthSession } from './auth-session';
describe('Deudas fijas',()=>{
  afterEach(()=>{localStorage.clear();});
  async function setup(){
    const debt:Commitment={id:'debt',espacio_id:'s',cuenta_id:'bank',nombre:'Casa',moneda:'ARS',importe:'100.00',categoria:null,primer_vencimiento:'2026-11-30',total_cuotas:2,cuotas_pagadas:0,total:'200.00',pagado:'0.00',pendiente:'200.00',proximo_vencimiento:'2026-11-30'};
    const quota:Installment={id:'quota',espacio_id:'s',compromiso_id:'debt',numero:1,vencimiento:'2026-11-30',importe:'100.00',pagado:'0.00',pendiente:'100.00',estado:'pendiente',vencida:false};
    const request=vi.fn().mockImplementation(async(method,path,body)=>method==='POST'?path.includes('/payments')?{...body,espacio_id:'s',cuota_id:'quota',moneda:'ARS'}:debt:
      path.includes('/installments?')?{items:[quota],next_offset:null}:path.includes('/payments?')?{items:[],next_offset:null}:{items:[debt],next_offset:null});
    TestBed.configureTestingModule({imports:[Commitments],providers:[{provide:AuthSession,useValue:{accountRequest:request}}]});
    const f=TestBed.createComponent(Commitments);f.componentRef.setInput('space','s');f.componentRef.setInput('accounts',[{id:'bank',nombre:'Banco'}]);
    f.detectChanges();await f.whenStable();f.detectChanges();return {f,c:f.componentInstance,request,debt,quota};
  }
  it('calcula el total como centavos exactos y conserva UUID al reintentar el alta',async()=>{
    const {c,request}=await setup();c.name='Casa';c.account='bank';c.amount='250,10';c.count=10;
    expect(c.total()).toBe('2.501,00');request.mockRejectedValue(new Error());await c.save();await c.save();
    const writes=request.mock.calls.filter(row=>row[0]==='POST');expect(writes[0][2]).toEqual(writes[1][2]);expect(writes[0][2].importe).toBe('250.10');
  });
  it('conserva el identificador de pago ante respuesta perdida',async()=>{
    const {c,request,debt,quota}=await setup();await c.choose(debt);await c.selectQuota(quota);c.payAmount='30,00';
    request.mockRejectedValue(new Error());await c.pay();await c.pay();
    const writes=request.mock.calls.filter(row=>row[0]==='POST');
    expect(writes).toHaveLength(2);expect(writes[0][2]).toEqual(writes[1][2]);expect(writes[0][2].importe).toBe('30.00');
    expect(c.payDirty).toBe(true);
  });
  it('rechaza pagos superiores al pendiente y actualiza el contenedor al guardar',async()=>{
    const {c,request,debt,quota}=await setup();await c.choose(debt);await c.selectQuota(quota);
    c.payAmount='101';await c.pay();expect(request.mock.calls.some(row=>row[0]==='POST')).toBe(false);
    const changed=vi.fn();c.changed.subscribe(changed);c.payAmount='30';await c.pay();
    expect(changed).toHaveBeenCalledOnce();expect(c.lastPayment()!.importe).toBe('30.00');
    expect(c.receiptPath(c.lastPayment()!)).toBe('/api/spaces/s/accounts/bank/expenses/'+c.lastPayment()!.id+'/receipts');
  });
  it('protege un pago en borrador al cambiar de cuota y oculta dinero',async()=>{
    const {f,c,debt,quota}=await setup();await c.choose(debt);await c.selectQuota(quota);c.payDirty=true;c.payAmount='30';
    await c.selectQuota({...quota,id:'other'});expect(c.quota()!.id).toBe('quota');expect(c.payAmount).toBe('30');
    window.dispatchEvent(new CustomEvent('gastos-privacy',{detail:true}));f.detectChanges();
    expect(f.nativeElement.textContent).not.toContain('200,00');expect(f.nativeElement.querySelector('#payment-amount')).toBeNull();
  });
  it('ignora el guardado al destruir la pantalla',async()=>{
    const {f,c,request}=await setup();let finish!:(v:unknown)=>void;request.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
    c.name='Casa';c.account='bank';c.amount='10';const task=c.save();f.destroy();finish({});await task;
    expect(c.notice()).toBe('');
  });
});
