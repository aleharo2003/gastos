import { Component, DestroyRef, inject, Input, OnInit, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthSession } from './auth-session';

type Similar = {id:string;descripcion:string;fecha:string;importe:string;moneda:string;categoria?:string|null;coincidencia_aproximada?:boolean};

@Component({selector:'app-similar-expenses',templateUrl:'./similar-expenses.html',styleUrl:'./similar-expenses.css'})
export class SimilarExpenses implements OnInit {
  @Input({required:true}) path='';
  @Input() categories: {id:string;label:string}[]=[];
  readonly items=signal<Similar[]>([]);
  readonly loading=signal(false);
  readonly error=signal('');
  private alive=true;
  private readonly auth=inject(AuthSession);
  constructor(){inject(DestroyRef).onDestroy(()=>{this.alive=false;});}
  ngOnInit(){void this.load();}
  categoryName(id?:string|null){return this.categories.find(c=>c.id===id)?.label ?? 'Sin categoría';}
  amount(value:string){const [whole,fraction]=value.split('.');return whole.replace(/\B(?=(\d{3})+(?!\d))/g,'.')+','+fraction;}
  async load(){
    if(this.loading())return;
    this.loading.set(true);this.error.set('');this.items.set([]);
    try {
      const result=await this.auth.accountRequest<{referencia_id:string;items:Similar[]}>('GET',this.path);
      if(this.alive)this.items.set(result.items);
    } catch(error) {
      if(this.alive)this.error.set(error instanceof HttpErrorResponse && [403,404].includes(error.status)
        ? 'Este gasto ya no está disponible para consultar. Actualizá la lista.'
        : 'No pudimos consultar gastos similares. Podés volver a intentar.');
    } finally {if(this.alive)this.loading.set(false);}
  }
}
