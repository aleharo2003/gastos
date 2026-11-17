import { Component, DestroyRef, EventEmitter, inject, Input, OnChanges, Output, signal, SimpleChanges } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthSession } from './auth-session';
import { normalizeAmount, showAmount } from './expenses';

type Payload={id:string;origen_id:string;destino_id:string;fecha:string;descripcion:string;moneda:string;importe:string};
type Transfer=Payload & {espacio_id:string};
type Page={items:Transfer[];next_offset:number|null};
@Component({selector:'app-transfers',imports:[FormsModule],templateUrl:'./transfers.html',styleUrl:'./transfers.css'})
export class Transfers implements OnChanges {
  @Input({required:true}) space='';
  @Input() accounts:{id:string;nombre:string}[]=[];
  @Input() moreAccounts=false;
  @Input() accountsLoading=false;
  @Output() loadAccounts=new EventEmitter<void>();
  @Output() changed=new EventEmitter<void>();
  @Output() viewAccount=new EventEmitter<string>();
  readonly items=signal<Transfer[]>([]);
  readonly next=signal<number|null>(null);
  readonly loading=signal(false);
  readonly saving=signal(false);
  readonly error=signal('');
  readonly notice=signal('');
  readonly hidden=signal(false);
  savedDestination='';origin='';destination='';description='';amount='';currency='ARS';historyAccount='';
  date=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Argentina/Buenos_Aires',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  readonly showAmount=showAmount;
  private readonly auth=inject(AuthSession);
  private alive=true;
  private generation=0;
  private appliedAccount='';
  private pending?:Payload;
  private readonly privacyListener=(event:Event)=>this.hidden.set((event as CustomEvent).detail===true);
  constructor(){
    try{this.hidden.set(localStorage.getItem('gastos.totals.hidden')==='true');}catch{}
    window.addEventListener('gastos-privacy',this.privacyListener);
    inject(DestroyRef).onDestroy(()=>{this.alive=false;this.generation++;window.removeEventListener('gastos-privacy',this.privacyListener);});
  }
  ngOnChanges(changes:SimpleChanges){
    if(changes['space']){
      this.generation++;this.loading.set(false);this.saving.set(false);this.items.set([]);this.next.set(null);
      this.origin='';this.destination='';this.amount='';this.description='';this.pending=undefined;
      this.historyAccount='';this.appliedAccount='';this.savedDestination='';this.notice.set('');void this.load();
    }
  }
  accountName(id:string){return this.accounts.find(row=>row.id===id)?.nombre??id;}
  destinations(){return this.accounts.filter(row=>row.id!==this.origin);}
  originChanged(){if(this.origin===this.destination)this.destination='';}
  clear(){if(this.saving())return;this.pending=undefined;this.amount='';this.description='';this.error.set('');}
  private get path(){return `/api/spaces/${encodeURIComponent(this.space)}/transfers`;}
  async applyHistory(){
    if(this.loading()||this.saving())return;
    this.appliedAccount=this.historyAccount;await this.load();
  }
  async load(more=false){
    if(this.loading()||this.saving())return;
    const offset=more?this.next():0;if(offset===null)return;
    const generation=this.generation,params=new URLSearchParams({offset:String(offset)});
    if(this.appliedAccount)params.set('account',this.appliedAccount);
    this.loading.set(true);this.error.set('');
    try{
      const page=await this.auth.accountRequest<Page>('GET',this.path+'?'+params);
      if(!page||!Array.isArray(page.items))throw new Error();
      if(!this.alive||generation!==this.generation)return;
      this.items.set([...new Map((more?[...this.items(),...page.items]:page.items).map(row=>[row.id,row])).values()]);
      this.next.set(page.next_offset);
    }catch{if(this.alive&&generation===this.generation)this.error.set('No pudimos cargar las transferencias.');}
    finally{if(this.alive&&generation===this.generation)this.loading.set(false);}
  }
  async save(){
    if(this.saving()||this.loading())return;
    const amount=normalizeAmount(this.amount),description=this.description.trim();
    if(!this.origin||!this.destination||this.origin===this.destination||
        ![this.origin,this.destination].every(id=>this.accounts.some(row=>row.id===id))||
        !amount||!description||[...description].length>160||!this.date){
      this.error.set('Elegí dos cuentas distintas y completá fecha, descripción e importe positivo, con hasta dos decimales.');return;
    }
    const value={origen_id:this.origin,destino_id:this.destination,fecha:this.date,descripcion:description,moneda:this.currency,importe:amount};
    if(!this.pending||Object.entries(value).some(([key,v])=>this.pending![key as keyof Payload]!==v))this.pending={id:crypto.randomUUID(),...value};
    const payload=this.pending,generation=this.generation;
    this.saving.set(true);this.error.set('');this.notice.set('');
    try{
      const row=await this.auth.accountRequest<Transfer>('POST',this.path,payload);
      if(row.id!==payload.id||row.origen_id!==payload.origen_id||row.destino_id!==payload.destino_id)throw new Error();
      if(!this.alive||generation!==this.generation)return;
      this.pending=undefined;this.amount='';this.description='';this.savedDestination=payload.destino_id;
      this.notice.set('Transferencia registrada. Los saldos de ambas cuentas se actualizaron.');this.changed.emit();
    }catch(error){
      if(this.alive&&generation===this.generation)this.error.set(error instanceof HttpErrorResponse&&error.status===403
        ?'No tenés permiso para registrar transferencias.'
        :error instanceof HttpErrorResponse&&error.status===409?'El identificador corresponde a otra transferencia. Actualizá el historial para revisar lo registrado.'
        :'No pudimos confirmar el guardado. Reintentá con los mismos datos; esta solicitud no se duplicará.');
    }finally{if(this.alive&&generation===this.generation)this.saving.set(false);}
    if(this.alive&&generation===this.generation&&!this.pending)await this.load();
  }
}
