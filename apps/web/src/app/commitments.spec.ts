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
      path.includes('/installments?month=')?{mes:new URL('https://local'+path).searchParams.get('month'),items:[],totales:[],next_offset:null}:
      path.endsWith('/commitments/debt')?debt:path.includes('/installments?')?{items:[quota],next_offset:null}:path.includes('/payments?')?{items:[],next_offset:null}:{items:[debt],next_offset:null});
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
  it('muestra totales por moneda y oculta importes con privacidad',async()=>{
    const {f,c,request,quota}=await setup();
    request.mockResolvedValue({mes:'2026-11',items:[{...quota,nombre:'Casa',moneda:'ARS',cuenta_id:'bank'}],
      totales:[{moneda:'ARS',cuotas:1,cuotas_pagadas:0,total:'100.00',pagado:'30.00',pendiente:'70.00',vencido:'0.00'},
      {moneda:'USD',cuotas:2,cuotas_pagadas:1,total:'500.00',pagado:'250.00',pendiente:'250.00',vencido:'250.00'}],next_offset:null});
    c.month='2026-11';await c.loadMonth();f.detectChanges();
    const monthly=f.nativeElement.querySelector('.monthly');
    expect(monthly.textContent).toContain('70,00');expect(monthly.textContent).toContain('USD');expect(monthly.textContent).toContain('Vencido');
    window.dispatchEvent(new CustomEvent('gastos-privacy',{detail:true}));f.detectChanges();
    expect(monthly.textContent).not.toContain('70,00');expect(monthly.textContent).toContain('••••');
  });
  it('descarta respuestas de meses anteriores y conserva el mes visible ante error',async()=>{
    const {c,request}=await setup();let finish!:(value:unknown)=>void;
    request.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
    c.month='2026-10';const old=c.loadMonth();
    request.mockResolvedValueOnce({mes:'2026-12',items:[],totales:[],next_offset:null});
    c.month='2026-12';await c.loadMonth();
    finish({mes:'2026-10',items:[],totales:[],next_offset:null});await old;
    expect(c.appliedMonth()).toBe('2026-12');
    request.mockRejectedValueOnce(new Error());c.month='2027-01';await c.loadMonth();
    expect(c.appliedMonth()).toBe('2026-12');expect(c.monthError()).toBeTruthy();
  });
  it('abre cuotas fuera de la primera pagina del plan y protege el pago pendiente',async()=>{
    const {c,request,debt,quota}=await setup();const long={...debt,total_cuotas:101};
    const item={...quota,id:'last',numero:101,nombre:'Casa',moneda:'ARS',cuenta_id:'bank'};
    request.mockImplementation(async(_method,path)=>path.endsWith('/commitments/debt')?long:
      path.includes('/installments?offset=100')?{items:[item],next_offset:null}:{items:[],next_offset:null});
    c.items.set([]);await c.openMonthly(item);
    expect(c.selected()!.total_cuotas).toBe(101);expect(c.quota()!.id).toBe('last');expect(c.installmentOffset).toBe(100);
    c.payDirty=true;c.payAmount='30';const before=request.mock.calls.length;
    await c.openMonthly({...item,id:'different'});expect(request.mock.calls.length).toBe(before);expect(c.payAmount).toBe('30');
  });
  it('pagina el mes aplicado aunque el selector tenga un mes sin consultar',async()=>{
    const {c,request,quota}=await setup();c.appliedMonth.set('2026-11');c.month='2026-12';c.monthNext.set(100);
    request.mockResolvedValue({mes:'2026-11',items:[{...quota,nombre:'Casa',moneda:'ARS',cuenta_id:'bank'}],totales:[],next_offset:null});
    await c.loadMonth(true);
    expect(request.mock.calls.at(-1)![1]).toContain('month=2026-11&offset=100');
    expect(c.monthItems()).toHaveLength(1);
  });

  it('retira las cuotas del plan anterior si falla la apertura de otro',async()=>{
    const {c,request,debt,quota}=await setup();
    await c.choose(debt);expect(c.installments()[0].id).toBe(quota.id);
    request.mockRejectedValue(new Error());await c.choose({...debt,id:'other',nombre:'Otra deuda'});
    expect(c.selected()!.id).toBe('other');expect(c.installments()).toEqual([]);expect(c.quota()).toBeNull();
  });

});
