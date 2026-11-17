import { Component,DestroyRef,EventEmitter,inject,Input,OnChanges,Output,signal,SimpleChanges } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthSession } from './auth-session';
import { normalizeAmount,showAmount } from './expenses';

export type Goal={id:string;espacio_id:string;cuenta_id:string;cuenta_nombre:string;nombre:string;moneda:string;objetivo:string;
  fecha_objetivo:string|null;archivada:boolean;version:number;saldo:string;acumulado:string;faltante:string;porcentaje:string;alcanzada:boolean;vencida:boolean};
export type GoalTransfer={cuenta_id:string;cuenta_nombre:string;nombre:string;moneda:string;retirar:boolean};
type Create={id:string;cuenta_id:string;nombre:string;moneda:string;objetivo:string;fecha_objetivo:string|null};
@Component({selector:'app-savings-goals',imports:[FormsModule],templateUrl:'./savings-goals.html',styleUrl:'./savings-goals.css'})
export class SavingsGoals implements OnChanges {
  @Input({required:true}) space='';
  @Input() accounts:{id:string;nombre:string}[]=[];
  @Input() moreAccounts=false;
  @Input() accountsLoading=false;
  @Input() revision=0;
  @Output() loadAccounts=new EventEmitter<void>();
  @Output() prepareTransfer=new EventEmitter<GoalTransfer>();
  readonly items=signal<Goal[]>([]);
  readonly next=signal<number|null>(null);
  readonly loading=signal(false);
  readonly saving=signal(false);
  readonly error=signal('');
  readonly notice=signal('');
  readonly hidden=signal(false);
  name='';target='';account='';currency='ARS';deadline='';archived=false;includeArchived=false;
  editing:Goal|null=null;
  readonly showAmount=showAmount;
  readonly percent=(goal:Goal)=>Number(goal.porcentaje);
  private readonly auth=inject(AuthSession);
  private alive=true;private context=0;private readVersion=0;
  private appliedArchived=false;
  private pending?:Create;
  private readonly privacyListener=(event:Event)=>this.hidden.set((event as CustomEvent).detail===true);
  constructor(){
    try{this.hidden.set(localStorage.getItem('gastos.totals.hidden')==='true');}catch{}
    window.addEventListener('gastos-privacy',this.privacyListener);
    inject(DestroyRef).onDestroy(()=>{this.alive=false;this.context++;this.readVersion++;window.removeEventListener('gastos-privacy',this.privacyListener);});
  }
  ngOnChanges(changes:SimpleChanges){
    if(changes['space']){
      this.context++;this.readVersion++;this.saving.set(false);this.loading.set(false);
      this.reset();this.items.set([]);this.next.set(null);this.includeArchived=false;this.appliedArchived=false;
    }
    if(changes['space']||changes['revision'])void this.load();
  }
  private get path(){return `/api/spaces/${encodeURIComponent(this.space)}/savings-goals`;}
  hasDraft(){return !!(this.editing||this.name||this.target||this.deadline);}
  reset(){
    if(this.saving())return;
    this.editing=null;this.name='';this.target='';this.account='';this.currency='ARS';this.deadline='';this.archived=false;
    this.pending=undefined;this.error.set('');
  }
  edit(goal:Goal){
    if(this.loading()||this.saving())return;
    if(this.hasDraft()&&!window.confirm('¿Descartar el borrador actual y editar esta meta?'))return;
    this.editing=structuredClone(goal);this.name=goal.nombre;this.target=goal.objetivo;this.account=goal.cuenta_id;
    this.currency=goal.moneda;this.deadline=goal.fecha_objetivo??'';this.archived=goal.archivada;
    this.pending=undefined;this.error.set('');this.notice.set('');
  }
  prepare(goal:Goal,retirar=false){
    if(goal.archivada||this.saving())return;
    this.prepareTransfer.emit({cuenta_id:goal.cuenta_id,cuenta_nombre:goal.cuenta_nombre,nombre:goal.nombre,moneda:goal.moneda,retirar});
  }
  async applyArchived(){
    if(this.loading()||this.saving())return;
    this.appliedArchived=this.includeArchived;await this.load();
  }
  async load(more=false){
    if(this.saving()||(more&&this.loading()))return;
    const offset=more?this.next():0;if(offset===null)return;
    const version=++this.readVersion;
    this.loading.set(true);this.error.set('');
    try{
      const page=await this.auth.accountRequest<{items:Goal[];next_offset:number|null}>('GET',this.path+`?offset=${offset}&archived=${this.appliedArchived}`);
      if(!page||!Array.isArray(page.items))throw new Error();
      if(!this.alive||version!==this.readVersion)return;
      this.items.set([...new Map((more?[...this.items(),...page.items]:page.items).map(row=>[row.id,row])).values()]);
      this.next.set(page.next_offset);
    }catch{if(this.alive&&version===this.readVersion)this.error.set('No pudimos actualizar las metas. Los datos anteriores pueden haber cambiado.');}
    finally{if(this.alive&&version===this.readVersion)this.loading.set(false);}
  }
  async save(){
    if(this.saving()||this.loading())return;
    const nombre=this.name.trim(),objetivo=normalizeAmount(this.target);
    if(!nombre||[...nombre].length>160||!objetivo||!this.account||(!this.editing&&!this.accounts.some(row=>row.id===this.account))){
      this.error.set('Elegí una cuenta y completá el nombre y un objetivo positivo con hasta dos decimales.');return;
    }
    const values={nombre,objetivo,fecha_objetivo:this.deadline||null};
    let body:unknown,path=this.path,method:'POST'|'PATCH'='POST';
    if(this.editing){
      method='PATCH';path+='/'+encodeURIComponent(this.editing.id);
      body={...values,version:this.editing.version,archivada:this.archived};
    }else{
      const value={...values,cuenta_id:this.account,moneda:this.currency};
      if(!this.pending||Object.entries(value).some(([key,v])=>this.pending![key as keyof Create]!==v))this.pending={id:crypto.randomUUID(),...value};
      body=this.pending;
    }
    const context=this.context;this.saving.set(true);this.error.set('');this.notice.set('');
    let saved=false;
    try{
      await this.auth.accountRequest<Goal>(method,path,body);
      if(!this.alive||context!==this.context)return;
      saved=true;
    }catch(error){
      if(this.alive&&context===this.context)this.error.set(error instanceof HttpErrorResponse&&error.status===409
        ?'La meta cambió en otra sesión o ya existe una meta activa para esa cuenta y moneda. Tu borrador se conserva; actualizá la lista y revisalo.'
        :error instanceof HttpErrorResponse&&error.status===403?'No tenés permiso para modificar metas.'
        :'No pudimos confirmar el guardado. Reintentá con los mismos datos; tu borrador se conserva.');
    }finally{if(this.alive&&context===this.context)this.saving.set(false);}
    if(saved&&this.alive&&context===this.context){this.reset();this.notice.set('Meta guardada. No se movió dinero.');await this.load();}
  }
}
