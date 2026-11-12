import { Component, DestroyRef, inject, Input, OnChanges, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AuthSession } from './auth-session';
import { CurrencyTotal, cents, money, rateUnits, reference } from './money-reference';
type Summary={fecha:string;mes:string;totales:CurrencyTotal[]};
function argentinaDay() { return new Intl.DateTimeFormat('en-CA',{timeZone:'America/Argentina/Buenos_Aires',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date()); }
@Component({selector:'app-expense-totals',imports:[FormsModule],templateUrl:'./expense-totals.html',styleUrl:'./expense-totals.css'})
export class ExpenseTotals implements OnChanges {
  @Input({required:true}) space='';
  @Input() account='';
  @Input() revision=0;
  readonly data=signal<Summary|null>(null);
  readonly error=signal('');
  readonly hidden=signal(false);
  currency:'ARS'|'USD'='USD';
  rate=''; rateDate=''; draftRate=''; rateError='';
  private readonly auth=inject(AuthSession);
  private generation=0;
  private storedSpace='';
  private alive=true;
  constructor() {
    try { this.hidden.set(localStorage.getItem('gastos.totals.hidden')==='true'); } catch {}
    const privacy=(event:Event)=>this.hidden.set((event as CustomEvent).detail===true);
    window.addEventListener('gastos-privacy',privacy);
    inject(DestroyRef).onDestroy(()=>window.removeEventListener('gastos-privacy',privacy));
    const timer=setInterval(()=>{
      if(!document.hidden && this.data() && this.data()!.fecha!==argentinaDay()) void this.load();
    },60000);
    inject(DestroyRef).onDestroy(()=>{this.alive=false;this.generation++;clearInterval(timer);});
  }
  ngOnChanges() {
    if(this.storedSpace!==this.space) {
      this.storedSpace=this.space;this.rate='';this.rateDate='';this.draftRate='';
      try {
        const saved=JSON.parse(localStorage.getItem('gastos.reference.'+this.space) ?? 'null');
        if(saved && typeof saved.rate==='string' && rateUnits(saved.rate) && /^\d{4}-\d{2}-\d{2}$/.test(saved.date)) {
          this.rate=saved.rate;this.draftRate=saved.rate;this.rateDate=saved.date;
        }
      } catch {}
    }
    void this.load();
  }
  async load() {
    const generation=++this.generation;
    this.data.set(null);this.error.set('');
    try {
      const summary=await this.auth.accountRequest<Summary>('GET',`/api/spaces/${encodeURIComponent(this.space)}/expense-summary${this.account ? '?account='+encodeURIComponent(this.account) : ''}`);
      if(!summary || !Array.isArray(summary.totales) || typeof summary.fecha!=='string' || typeof summary.mes!=='string') throw new Error();
      for(const row of summary.totales) { cents(row.dia);cents(row.mes); }
      if(this.alive && generation===this.generation)this.data.set(summary);
    } catch { if(this.alive && generation===this.generation)this.error.set('No pudimos calcular los totales.'); }
  }
  total(period:'dia'|'mes'):string {
    const data=this.data();if(!data)return '—';
    const result=reference(data.totales,period,this.currency,rateUnits(this.rate));
    return result===null ? 'Conversión pendiente' : this.currency+' '+money(result);
  }
  native(value:string) {return money(cents(value));}
  toggle() {
    this.hidden.update(value=>!value);
    try { localStorage.setItem('gastos.totals.hidden',String(this.hidden())); } catch {}
    window.dispatchEvent(new CustomEvent('gastos-privacy',{detail:this.hidden()}));
  }
  saveRate() {
    if(!rateUnits(this.draftRate)) { this.rateError='Ingresá pesos por 1 USD, mayor que cero y hasta 4 decimales.';return; }
    this.rate=this.draftRate.trim().replace(',','.');this.rateDate=argentinaDay();this.rateError='';
    try { localStorage.setItem('gastos.reference.'+this.space,JSON.stringify({rate:this.rate,date:this.rateDate})); }
    catch { this.rateError='La referencia se aplicó, pero este navegador no permite guardarla.'; }
    window.dispatchEvent(new CustomEvent('gastos-reference',{detail:{space:this.space,rate:this.rate}}));
  }
}
