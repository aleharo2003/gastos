import { Component,DestroyRef,EventEmitter,inject,Input,OnChanges,Output,signal,SimpleChanges,ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthSession } from './auth-session';
import { Receipts } from './receipts';
import { normalizeAmount,showAmount } from './expenses';
import { cents,money } from './money-reference';
export type Commitment={id:string;espacio_id:string;cuenta_id:string;nombre:string;moneda:string;importe:string;categoria:string|null;
  primer_vencimiento:string;total_cuotas:number;cuotas_pagadas:number;total:string;pagado:string;pendiente:string;proximo_vencimiento:string|null};
export type Installment={id:string;espacio_id:string;compromiso_id:string;numero:number;vencimiento:string;importe:string;pagado:string;pendiente:string;estado:string;vencida:boolean};
export type Payment={id:string;espacio_id:string;cuota_id:string;cuenta_id:string;fecha:string;moneda:string;importe:string};
export type MonthlyItem=Installment & {nombre:string;moneda:string;cuenta_id:string};
export type MonthlyTotal={moneda:string;cuotas:number;cuotas_pagadas:number;total:string;pagado:string;pendiente:string;vencido:string};
export type MonthlyPage={mes:string;items:MonthlyItem[];totales:MonthlyTotal[];next_offset:number|null};
type Create={id:string;cuenta_id:string;nombre:string;moneda:string;importe:string;categoria:string|null;primer_vencimiento:string;total_cuotas:number};
type Pay={id:string;cuenta_id:string;fecha:string;importe:string};
const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'America/Argentina/Buenos_Aires',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
@Component({selector:'app-commitments',imports:[FormsModule,Receipts],templateUrl:'./commitments.html',styleUrl:'./commitments.css'})
export class Commitments implements OnChanges{
  @Input({required:true}) space='';
  @Input() accounts:{id:string;nombre:string}[]=[];
  @Input() moreAccounts=false;
  @Input() accountsLoading=false;
  @Output() loadAccounts=new EventEmitter<void>();
  @Output() changed=new EventEmitter<void>();
  @ViewChild(Receipts) receiptPanel?:Receipts;
  readonly items=signal<Commitment[]>([]);
  readonly next=signal<number|null>(null);
  readonly installments=signal<Installment[]>([]);
  readonly nextInstallment=signal<number|null>(null);
  readonly payments=signal<Payment[]>([]);
  readonly nextPayment=signal<number|null>(null);
  readonly selected=signal<Commitment|null>(null);
  readonly quota=signal<Installment|null>(null);
  readonly receiptPayment=signal<Payment|null>(null);
  readonly lastPayment=signal<Payment|null>(null);
  month=today().slice(0,7);
  readonly appliedMonth=signal('');
  readonly monthItems=signal<MonthlyItem[]>([]);
  readonly monthTotals=signal<MonthlyTotal[]>([]);
  readonly monthNext=signal<number|null>(null);
  readonly monthLoading=signal(false);
  readonly monthError=signal('');
  private monthVersion=0;
  readonly loading=signal(false);readonly detailLoading=signal(false);readonly historyLoading=signal(false);
  readonly saving=signal(false);readonly paying=signal(false);readonly error=signal('');readonly notice=signal('');
  readonly hidden=signal(false);
  name='';account='';currency='ARS';amount='';category='';first=today();count=10;
  payAccount='';payDate=today();payAmount='';payDirty=false;installmentOffset=0;
  readonly showAmount=showAmount;
  readonly categories=[['alimentos','Alimentos'],['transporte','Transporte'],['vivienda','Vivienda'],['servicios','Servicios'],['salud','Salud'],['educacion','Educación'],['ocio','Ocio'],['impuestos','Impuestos'],['auto','Auto'],['bancario','Bancario'],['ropa','Ropa'],['otros','Otros']];
  private readonly auth=inject(AuthSession);private alive=true;private context=0;private detailVersion=0;private historyVersion=0;
  private pending?:Create;private payPending?:{quota:string;body:Pay};
  private readonly privacyListener=(event:Event)=>this.hidden.set((event as CustomEvent).detail===true);
  constructor(){
    try{this.hidden.set(localStorage.getItem('gastos.totals.hidden')==='true');}catch{}
    window.addEventListener('gastos-privacy',this.privacyListener);
    inject(DestroyRef).onDestroy(()=>{this.alive=false;this.context++;this.detailVersion++;this.historyVersion++;window.removeEventListener('gastos-privacy',this.privacyListener);});
  }
  ngOnChanges(changes:SimpleChanges){if(changes['space']){
    this.context++;this.detailVersion++;this.historyVersion++;this.monthVersion++;this.monthLoading.set(false);this.monthItems.set([]);this.monthTotals.set([]);this.monthNext.set(null);this.appliedMonth.set('');this.monthError.set('');this.month=today().slice(0,7);this.loading.set(false);this.saving.set(false);this.paying.set(false);
    this.detailLoading.set(false);this.historyLoading.set(false);this.items.set([]);this.selected.set(null);this.quota.set(null);
    this.installments.set([]);this.payments.set([]);this.next.set(null);this.nextInstallment.set(null);this.nextPayment.set(null);
    this.receiptPayment.set(null);this.lastPayment.set(null);this.clear();this.payAmount='';this.payPending=undefined;this.payDirty=false;void this.load();void this.loadMonth();
  }}
  private get path(){return `/api/spaces/${encodeURIComponent(this.space)}`;}
  total(){const amount=normalizeAmount(this.amount);return amount&&Number.isInteger(this.count)&&this.count>=1&&this.count<=600?money(cents(amount)*BigInt(this.count)):null;}
  accountName(id:string){return this.accounts.find(row=>row.id===id)?.nombre??id;}
  clear(){if(this.saving())return;this.pending=undefined;this.name='';this.amount='';this.category='';this.account='';this.currency='ARS';this.first=today();this.count=10;}
  private receiptBusy(){return !!(this.receiptPanel?.busy()||this.receiptPanel?.selected());}
  private canLeave(){if(this.paying()||this.receiptBusy()||this.payDirty){this.error.set('Terminá o cancelá el pago y los comprobantes pendientes antes de cambiar.');return false;}return true;}
  cancelPayment(){if(this.paying()||this.receiptBusy())return;this.payPending=undefined;this.payDirty=false;this.payAmount='';this.quota.set(null);this.payments.set([]);this.historyVersion++;this.historyLoading.set(false);this.receiptPayment.set(null);this.nextPayment.set(null);}
  receiptPath(p:Payment){return this.path+'/accounts/'+encodeURIComponent(p.cuenta_id)+'/expenses/'+encodeURIComponent(p.id)+'/receipts';}
  receipts(p:Payment){if(this.paying()||this.receiptBusy()){this.error.set('Terminá el comprobante pendiente antes de abrir otro.');return;}this.receiptPayment.set(p);}
  async loadMonth(more=false){
    if(this.saving()||this.paying())return;
    const month=more?this.appliedMonth():this.month;
    if(!/^[0-9]{4}-(0[1-9]|1[0-2])$/.test(month)||month.startsWith('0000')){this.monthError.set('Elegí un mes válido.');return;}
    const offset=more?this.monthNext():0;if(offset===null||(more&&this.monthLoading()))return;
    const version=++this.monthVersion,context=this.context;this.monthLoading.set(true);this.monthError.set('');
    try{
      const page=await this.auth.accountRequest<MonthlyPage>('GET',this.path+'/installments?month='+month+'&offset='+offset);
      if(!this.alive||context!==this.context||version!==this.monthVersion)return;
      if(page.mes!==month||!Array.isArray(page.items)||!Array.isArray(page.totales))throw new Error('Resumen mensual inválido');
      this.appliedMonth.set(page.mes);this.monthTotals.set(page.totales);
      this.monthItems.set([...new Map((more?[...this.monthItems(),...page.items]:page.items).map(row=>[row.id,row])).values()]);
      this.monthNext.set(page.next_offset);
    }catch{if(this.alive&&context===this.context&&version===this.monthVersion)this.monthError.set('No pudimos cargar el resumen mensual. Los datos visibles conservan su mes indicado.');}
    finally{if(this.alive&&context===this.context&&version===this.monthVersion)this.monthLoading.set(false);}
  }
  async openMonthly(item:MonthlyItem){
    if(!this.canLeave()||this.detailLoading()||this.saving())return;
    const context=this.context;this.detailLoading.set(true);this.error.set('');
    let debt:Commitment|null=null;
    try{debt=await this.auth.accountRequest<Commitment>('GET',this.path+'/commitments/'+encodeURIComponent(item.compromiso_id));}
    catch{if(this.alive&&context===this.context)this.error.set('No pudimos abrir la deuda. Reintentá desde el resumen.');}
    finally{if(this.alive&&context===this.context)this.detailLoading.set(false);}
    if(!debt||!this.alive||context!==this.context||!this.canLeave())return;
    this.cancelPayment();this.selected.set(debt);this.installments.set([]);this.nextInstallment.set(null);this.lastPayment.set(null);
    await this.loadInstallments(Math.floor((item.numero-1)/100)*100);
    const quota=this.installments().find(row=>row.id===item.id);
    if(quota)await this.selectQuota(quota);
  }
  async load(more=false){
    if(this.loading()||this.saving()||this.paying())return;const offset=more?this.next():0;if(offset===null)return;
    const context=this.context;this.loading.set(true);this.error.set('');
    try{const page=await this.auth.accountRequest<{items:Commitment[];next_offset:number|null}>('GET',this.path+'/commitments?offset='+offset);
      if(!this.alive||context!==this.context)return;
      this.items.set([...new Map((more?[...this.items(),...page.items]:page.items).map(row=>[row.id,row])).values()]);this.next.set(page.next_offset);
      if(this.selected())this.selected.set(this.items().find(row=>row.id===this.selected()!.id)??this.selected());
    }catch{if(this.alive&&context===this.context)this.error.set('No pudimos cargar las deudas.');}
    finally{if(this.alive&&context===this.context)this.loading.set(false);}
  }
  async choose(item:Commitment){if(!this.canLeave()||this.detailLoading()||this.saving())return;this.cancelPayment();this.selected.set(item);this.installments.set([]);this.nextInstallment.set(null);this.lastPayment.set(null);await this.loadInstallments(0);}
  async loadInstallments(offset=this.installmentOffset){
    const selected=this.selected();if(!selected||this.detailLoading()||this.paying())return;
    if(offset!==this.installmentOffset&&!this.canLeave())return;
    const version=++this.detailVersion;this.detailLoading.set(true);this.error.set('');
    try{const page=await this.auth.accountRequest<{items:Installment[];next_offset:number|null}>('GET',this.path+'/commitments/'+encodeURIComponent(selected.id)+'/installments?offset='+offset);
      if(!this.alive||version!==this.detailVersion)return;
      this.installmentOffset=offset;this.installments.set(page.items);this.nextInstallment.set(page.next_offset);
      if(this.quota()){const current=page.items.find(row=>row.id===this.quota()!.id);if(current)this.quota.set(current);else this.cancelPayment();}
    }catch{if(this.alive&&version===this.detailVersion)this.error.set('No pudimos cargar las cuotas.');}
    finally{if(this.alive&&version===this.detailVersion)this.detailLoading.set(false);}
  }
  async selectQuota(item:Installment){
    if(!this.canLeave()||this.saving())return;
    this.cancelPayment();this.quota.set(item);this.payAccount=this.selected()?.cuenta_id??'';
    this.payDate=today();this.payAmount=item.pendiente==='0.00'?'':item.pendiente;await this.loadPayments();
  }
  async loadPayments(more=false){
    const quota=this.quota();if(!quota||this.historyLoading()||this.paying())return;
    const offset=more?this.nextPayment():0;if(offset===null)return;
    const version=++this.historyVersion;this.historyLoading.set(true);
    try{const page=await this.auth.accountRequest<{items:Payment[];next_offset:number|null}>('GET',this.path+'/installments/'+encodeURIComponent(quota.id)+'/payments?offset='+offset);
      if(!this.alive||version!==this.historyVersion)return;
      this.payments.set([...new Map((more?[...this.payments(),...page.items]:page.items).map(row=>[row.id,row])).values()]);this.nextPayment.set(page.next_offset);
    }catch{if(this.alive&&version===this.historyVersion)this.error.set('No pudimos cargar el historial de pagos.');}
    finally{if(this.alive&&version===this.historyVersion)this.historyLoading.set(false);}
  }
  async save(){
    if(this.saving()||this.loading()||this.paying())return;
    const importe=normalizeAmount(this.amount),nombre=this.name.trim();
    if(!importe||!nombre||[...nombre].length>160||!this.accounts.some(a=>a.id===this.account)||!Number.isInteger(this.count)||this.count<1||this.count>600||!this.first){this.error.set('Revisá nombre, cuenta, importe positivo, primer vencimiento y cantidad de 1 a 600 cuotas.');return;}
    const value={cuenta_id:this.account,nombre,moneda:this.currency,importe,categoria:this.category||null,primer_vencimiento:this.first,total_cuotas:this.count};
    if(!this.pending||Object.entries(value).some(([key,v])=>this.pending![key as keyof Create]!==v))this.pending={id:crypto.randomUUID(),...value};
    const context=this.context;this.saving.set(true);this.error.set('');this.notice.set('');let saved:Commitment|null=null;
    try{saved=await this.auth.accountRequest<Commitment>('POST',this.path+'/commitments',this.pending);}
    catch(error){if(this.alive&&context===this.context)this.error.set(error instanceof HttpErrorResponse&&error.status===403?'No tenés permiso para crear deudas.':'No pudimos confirmar el guardado. Reintentá con los mismos datos; no se duplicará el plan.');}
    finally{if(this.alive&&context===this.context)this.saving.set(false);}
    if(saved&&this.alive&&context===this.context){this.clear();this.notice.set('Deuda guardada con su calendario. No se descontó dinero.');await this.load();await this.loadMonth();await this.choose(saved);}
  }
  async pay(){
    const quota=this.quota();if(!quota||this.paying()||this.detailLoading()||this.saving()||this.receiptBusy())return;
    const importe=normalizeAmount(this.payAmount);
    if(!importe||!this.payDate||!this.accounts.some(a=>a.id===this.payAccount)||cents(importe)>cents(quota.pendiente)){this.error.set('Elegí una cuenta y un importe positivo que no supere el saldo de la cuota.');return;}
    const value={cuenta_id:this.payAccount,fecha:this.payDate,importe};
    if(!this.payPending||this.payPending.quota!==quota.id||Object.entries(value).some(([key,v])=>this.payPending!.body[key as keyof Pay]!==v))this.payPending={quota:quota.id,body:{id:crypto.randomUUID(),...value}};
    const context=this.context;this.paying.set(true);this.payDirty=true;this.error.set('');this.notice.set('');let saved:Payment|null=null;
    try{saved=await this.auth.accountRequest<Payment>('POST',this.path+'/installments/'+encodeURIComponent(quota.id)+'/payments',this.payPending.body);}
    catch(error){if(this.alive&&context===this.context)this.error.set(error instanceof HttpErrorResponse&&error.status===409
      ?'El saldo pendiente cambió o el identificador ya fue usado. Actualizá las cuotas para revisar el pago; tu formulario se conserva.'
      :error instanceof HttpErrorResponse&&error.status===403?'No tenés permiso para registrar pagos.'
      :'No pudimos confirmar el pago. Reintentá con los mismos datos; esta solicitud no se duplicará.');}
    finally{if(this.alive&&context===this.context)this.paying.set(false);}
    if(saved&&this.alive&&context===this.context){
      this.payPending=undefined;this.payDirty=false;this.payAmount='';this.lastPayment.set(saved);
      this.notice.set('Pago registrado. El gasto y el saldo de la deuda se actualizaron juntos.');this.changed.emit();
      await this.load();await this.loadInstallments();await this.loadPayments();await this.loadMonth();
    }
  }
}
