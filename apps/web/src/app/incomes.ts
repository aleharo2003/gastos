import { Component, DestroyRef, EventEmitter, inject, Input, OnChanges, Output, signal, SimpleChanges } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthSession } from './auth-session';
import { CategoryCatalog } from './category-catalog';
import { normalizeAmount, showAmount } from './expenses';

type Payload={id:string;fecha:string;descripcion:string;moneda:string;importe:string;categoria?:string|null};
type Income=Payload & {espacio_id:string;cuenta_id:string; cuenta_nombre?: string };
type Page={items:Income[];next_offset:number|null};
type Balance={totales:{moneda:string;ingresos:string;gastos:string;saldo:string;transferencias_entrada?:string;transferencias_salida?:string}[]};
@Component({selector:'app-incomes',imports:[FormsModule],templateUrl:'./incomes.html',styleUrl:'./incomes.css'})
export class Incomes implements OnChanges {
  @Input({required:true}) space='';
  @Input({required:true}) account={id:'',nombre:''};
  @Input() accounts:{id:string;nombre:string}[]=[];
  @Input() revision=0;
  @Output() changed=new EventEmitter<void>();
  readonly items=signal<Income[]>([]);
  readonly balance=signal<Balance|null>(null);
  readonly next=signal<number|null>(null);
  readonly loading=signal(false);
  readonly saving=signal(false);
  readonly error=signal('');
  readonly balanceError=signal('');
  readonly notice=signal('');
  readonly hidden=signal(false);
  createAccount='';description='';amount='';currency='ARS';
  category = '';
  date=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Argentina/Buenos_Aires',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  readonly showAmount=showAmount;
  private readonly auth=inject(AuthSession);
  private readonly catalog = inject(CategoryCatalog);
  private alive=true;
  private generation=0;
  private balanceGeneration=0;
  private pending?:{account:string;payload:Payload};
  private readonly privacyListener=(event:Event)=>this.hidden.set((event as CustomEvent).detail===true);
  constructor(){
    try{this.hidden.set(localStorage.getItem('gastos.totals.hidden')==='true');}catch{}
    window.addEventListener('gastos-privacy',this.privacyListener);
    inject(DestroyRef).onDestroy(()=>{this.alive=false;this.generation++;this.balanceGeneration++;window.removeEventListener('gastos-privacy',this.privacyListener);});
  }
  ngOnChanges(changes:SimpleChanges){
    if(changes['space']||changes['account']){
      this.generation++;this.loading.set(false);this.saving.set(false);this.items.set([]);this.next.set(null);
      this.pending=undefined;this.description='';this.amount='';this.category='';this.createAccount='';this.notice.set('');
      void this.load();
    }
    if(changes['space']||changes['account']||changes['revision'])void this.loadBalance();
  }
  hasPendingWork(){return this.saving() || !!(this.description || this.amount || this.category);}
  openEntry(): void {
    setTimeout(() => {
      if (this.alive) document.getElementById('income-title')?.focus();
    });
  }
  cancel(){if(this.saving())return;this.description='';this.amount='';this.category='';this.pending=undefined;this.error.set('');}
  get categories() { return this.catalog.categories(this.space, 'ingreso').filter(row => row.activa); }
  categoryName(id: string) { return this.catalog.label(this.space, 'ingreso', id); }
  accountName(id:string, historicalName?: string){return this.accounts.find(row=>row.id===id)?.nombre??historicalName??'Cuenta';}
  private get path(){return `/api/spaces/${encodeURIComponent(this.space)}`;}
  private get listPath(){return this.path+(this.account.id?'/accounts/'+encodeURIComponent(this.account.id):'')+'/incomes';}
  async loadBalance(){
    const generation=++this.balanceGeneration;
    this.balance.set(null);this.balanceError.set('');
    try{
      const value=await this.auth.accountRequest<Balance>('GET',this.path+'/account-balance'+(this.account.id?'?account='+encodeURIComponent(this.account.id):''));
      if(!value || !Array.isArray(value.totales))throw new Error();
      if(this.alive&&generation===this.balanceGeneration)this.balance.set(value);
    }catch{if(this.alive&&generation===this.balanceGeneration)this.balanceError.set('No pudimos actualizar el saldo. Volvé a intentar.');}
  }
  async load(more=false){
    if(this.loading()||this.saving())return;
    const offset=more?this.next():0;if(offset===null)return;
    const generation=this.generation;this.loading.set(true);this.error.set('');
    try{
      const page=await this.auth.accountRequest<Page>('GET',this.listPath+'?offset='+offset);
      if(!page || !Array.isArray(page.items))throw new Error();
      if(!this.alive||generation!==this.generation)return;
      this.items.set([...new Map((more?[...this.items(),...page.items]:page.items).map(row=>[row.id,row])).values()]);
      this.next.set(page.next_offset);
    }catch{if(this.alive&&generation===this.generation)this.error.set('No pudimos cargar los ingresos.');}
    finally{if(this.alive&&generation===this.generation)this.loading.set(false);}
  }
  async save(){
    if(this.saving()||this.loading())return;
    const account=this.account.id||this.createAccount,amount=normalizeAmount(this.amount),description=this.description.trim();
    if(!account || !this.accounts.some(row=>row.id===account) || !amount || !description || [...description].length>160 || !this.date){
      this.error.set('Elegí una cuenta y completá fecha, descripción e importe positivo, con hasta dos decimales.');return;
    }
    const value={fecha:this.date,descripcion:description,moneda:this.currency,importe:amount,
      ...((this.category || this.pending?.payload.categoria) ? { categoria: this.category || null } : {})};
    if(!this.pending || this.pending.account!==account || Object.entries(value).some(([key,v])=>this.pending!.payload[key as keyof Payload]!==v)){
      this.pending={account,payload:{id:crypto.randomUUID(),...value}};
    }
    const generation=this.generation;this.saving.set(true);this.error.set('');this.notice.set('');
    try{
      await this.auth.accountRequest<Income>('POST',this.path+'/accounts/'+encodeURIComponent(account)+'/incomes',this.pending.payload);
      if(!this.alive||generation!==this.generation)return;
      this.pending=undefined;this.description='';this.amount='';this.category='';this.notice.set('Ingreso registrado.');this.changed.emit();
    }catch(error){
      if(this.alive&&generation===this.generation)this.error.set(error instanceof HttpErrorResponse&&error.status===403
        ?'No tenés permiso para registrar ingresos.'
        :error instanceof HttpErrorResponse&&error.status===409?'La solicitud cambió. Actualizá los ingresos para revisar lo registrado.'
        :error instanceof HttpErrorResponse&&error.status===422&&this.category?'Revisá los datos y elegí una categoría activa o dejala vacía.'
        :'No pudimos confirmar el guardado. Reintentá con los mismos datos; la solicitud no se duplicará.');
    }finally{if(this.alive&&generation===this.generation)this.saving.set(false);}
    if(this.alive&&generation===this.generation&&!this.pending){await this.load();await this.loadBalance();}
  }
}
