import { Component, computed, DestroyRef, EventEmitter, inject, Input, OnChanges, Output, signal, SimpleChanges } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthSession } from './auth-session';
import { CurrencyTotal,cents,money,rateUnits,reference } from './money-reference';
import { emptyPlan,normalizedAmount,PlanData,PlanEnvelope,LimitPeriod,projected,progress,limitUsage,usageAgainstLimit } from './planning-math';
import { EXPENSE_CATEGORIES } from './expense-categories';
import { CategoryCatalog } from './category-catalog';

type CategorySpending = { desde: string; hasta: string; items: { categoria: string | null; moneda: string; total: string }[] };
type Summary={fecha:string;mes:string;semana_desde:string;semana_hasta:string;totales:CurrencyTotal[]};
@Component({selector:'app-planning',imports:[FormsModule],templateUrl:'./planning.html',styleUrl:'./planning.css'})
export class Planning implements OnChanges {
  @Input({required:true}) space='';
  @Input() compact=true;
  @Input() showCategoryAlerts = false;
  @Input() revision=0;
  @Output() configure=new EventEmitter<void>();
  readonly saved=signal<PlanEnvelope|null>(null);
  readonly summary=signal<Summary|null>(null);
  readonly loading=signal(false);
  readonly saving=signal(false);
  readonly error=signal('');
  readonly usageError=signal('');
  readonly notice=signal('');
  readonly hidden=signal(false);
  readonly rate=signal('');
  readonly categorySpending = signal<CategorySpending | null>(null);
  readonly categoryError = signal(false);
  categoryToAdd = '';
  private categoryRequest = 0;

  readonly categoryUsage = computed(() => {
    const spending = this.categorySpending();
    const rate = rateUnits(this.rate());
    return (this.saved()?.datos.limites_categoria ?? []).map(limit => {
      const totals = spending?.items.filter(row => row.categoria === limit.categoria)
        .map(row => ({ moneda: row.moneda, mes: row.total }));
      const spent = totals ? reference(totals, 'mes', limit.moneda, rate) : null;
      return { categoria: limit.categoria, ...usageAgainstLimit(limit, spent) };
    });
  });
  readonly categoryComparison = computed(() => {
    const report = this.categorySpending();
    if (!report) return null;
    const budgeted = new Set(this.categoryUsage().map(row => row.categoria));
    const unbudgeted = new Map<string | null, Map<string, bigint>>();
    const totals = new Map<string, bigint>();
    for (const row of report.items) {
      const amount = cents(row.total);
      totals.set(row.moneda, (totals.get(row.moneda) ?? 0n) + amount);
      if (row.categoria !== null && budgeted.has(row.categoria)) continue;
      const currencies = unbudgeted.get(row.categoria) ?? new Map<string, bigint>();
      currencies.set(row.moneda, (currencies.get(row.moneda) ?? 0n) + amount);
      unbudgeted.set(row.categoria, currencies);
    }
    return {
      month: report.desde.slice(0, 7),
      totals: [...totals],
      unbudgeted: [...unbudgeted].map(([category, amounts]) => ({
        category, label: category === null ? 'Sin categoría' : this.categoryLabel(category),
        amounts: [...amounts],
      })).sort((a, b) => a.label.localeCompare(b.label, 'es-AR')),
    };
  });
  readonly categoryAlerts = computed(() => this.hidden()
    ? []
    : this.categoryUsage().filter(item => item.progress?.warning));

  currency:'ARS'|'USD'='USD';
  draft:PlanData=emptyPlan();
  daily='';weekly='';dailyCurrency:'ARS'|'USD'='USD';weeklyCurrency:'ARS'|'USD'='USD';
  monthly = '';
  monthlyCurrency: 'ARS' | 'USD' = 'ARS';
  dirty=false;
  private alive=true;private generation=0;private usageGeneration=0;
  private readonly auth=inject(AuthSession);
  private readonly catalog = inject(CategoryCatalog);
  private readonly rateListener=(event:Event)=>{const detail=(event as CustomEvent).detail;if(detail?.space===this.space && typeof detail.rate==='string')this.rate.set(detail.rate);};
  private readonly privacyListener=(event:Event)=>this.hidden.set((event as CustomEvent).detail===true);
  constructor(){
    try{this.hidden.set(localStorage.getItem('gastos.totals.hidden')==='true');}catch{}
    window.addEventListener('gastos-reference',this.rateListener);window.addEventListener('gastos-privacy',this.privacyListener);
    const timer=setInterval(()=>{
      if(!document.hidden && this.summary() && this.summary()!.fecha!==new Intl.DateTimeFormat('en-CA',{timeZone:'America/Argentina/Buenos_Aires',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())) {
        void this.loadUsage();
        void this.loadCategoryUsage();
      }
    },60000);
    inject(DestroyRef).onDestroy(()=>{this.alive=false;this.generation++;this.usageGeneration++;this.categoryRequest++;clearInterval(timer);window.removeEventListener('gastos-reference',this.rateListener);window.removeEventListener('gastos-privacy',this.privacyListener);});
  }
  ngOnChanges(changes:SimpleChanges){
    if(changes['space']){
      this.generation++;this.loading.set(false);this.saving.set(false);this.notice.set('');
      this.saved.set(null);this.draft=emptyPlan();this.dirty=false;this.rate.set('');
      this.categoryRequest++;
      this.categorySpending.set(null);
      this.categoryError.set(false);
      this.categoryToAdd = '';
      try{const value=JSON.parse(localStorage.getItem('gastos.reference.'+this.space)??'null');if(typeof value?.rate==='string'&&rateUnits(value.rate))this.rate.set(value.rate);}catch{}
      void this.load();
    }
    if(changes['space']||changes['revision'])void this.loadUsage();
    if (!changes['space'] && (changes['compact'] || changes['revision'] || changes['showCategoryAlerts'])) void this.loadCategoryUsage();
  }
  private get path(){return `/api/spaces/${encodeURIComponent(this.space)}/spending-plan`;}
  private accept(value:PlanEnvelope){
    this.saved.set(value);this.draft=structuredClone(value.datos);
    this.categoryToAdd = '';
    void this.loadCategoryUsage();
    this.daily=value.datos.limites.diario?.importe??'';this.weekly=value.datos.limites.semanal?.importe??'';
    this.monthly = value.datos.limites.mensual?.importe ?? '';
    this.monthlyCurrency = value.datos.limites.mensual?.moneda ?? 'ARS';
    this.dailyCurrency=value.datos.limites.diario?.moneda??'USD';this.weeklyCurrency=value.datos.limites.semanal?.moneda??'USD';this.dirty=false;
  }
  async load(){
    if(this.loading()||this.saving())return;
    if(this.dirty&&!window.confirm('¿Descartar el borrador y cargar el presupuesto guardado?'))return;
    const generation=++this.generation;this.loading.set(true);this.error.set('');
    try{const value=await this.auth.accountRequest<PlanEnvelope>('GET',this.path);if(!value?.datos?.limites||!Array.isArray(value.datos.conceptos)||!Number.isInteger(value.version))throw new Error();if(this.alive&&generation===this.generation)this.accept(value);}
    catch{if(this.alive&&generation===this.generation)this.error.set('No pudimos cargar el presupuesto.');}
    finally{if(this.alive&&generation===this.generation)this.loading.set(false);}
  }
  async loadUsage(){
    const generation=++this.usageGeneration;this.summary.set(null);this.usageError.set('');
    try{
      const value=await this.auth.accountRequest<Summary>('GET',`/api/spaces/${encodeURIComponent(this.space)}/expense-summary`);
      if(!value?.semana_desde||!value.semana_hasta||!Array.isArray(value.totales))throw new Error();
      for(const row of value.totales){cents(row.dia);cents(row.mes);cents(row.semana??'invalid');}
      if(this.alive&&generation===this.usageGeneration)this.summary.set(value);
    }catch{if(this.alive&&generation===this.usageGeneration)this.usageError.set('No pudimos actualizar el consumo global.');}
  }
  async loadCategoryUsage(): Promise<void> {
    const request = ++this.categoryRequest;
    this.categorySpending.set(null);
    this.categoryError.set(false);
    const plan = this.saved();
    if (!plan || (this.compact && (!this.showCategoryAlerts || !plan.datos.limites_categoria?.length))) return;
    try {
      const report = await this.auth.accountRequest<CategorySpending>(
        'GET', `/api/spaces/${encodeURIComponent(this.space)}/expense-category-summary`,
      );
      if (!Array.isArray(report?.items)) throw new Error('Reporte inválido');
      for (const row of report.items) cents(row.total);
      if (this.alive && request === this.categoryRequest) this.categorySpending.set(report);
    } catch {
      if (this.alive && request === this.categoryRequest) this.categoryError.set(true);
    }
  }

  availableCategories() {
    return EXPENSE_CATEGORIES.filter(category =>
      !this.draft.limites_categoria?.some(row => row.categoria === category.id));
  }

  categoryLabel(id: string): string {
    return this.catalog.label(this.space, 'gasto', id);
  }

  addCategoryLimit(): void {
    if (!this.availableCategories().some(category => category.id === this.categoryToAdd)) return;
    (this.draft.limites_categoria ??= []).push({ categoria: this.categoryToAdd, moneda: 'ARS', importe: '' });
    this.categoryToAdd = '';
    this.dirty = true;
  }

  removeCategoryLimit(id: string): void {
    this.draft.limites_categoria = (this.draft.limites_categoria ?? []).filter(limit => limit.categoria !== id);
    this.dirty = true;
  }

  async save(){
    if(this.saving()||this.loading()||!this.saved())return;
    const diario=this.daily.trim()?normalizedAmount(this.daily):null,semanal=this.weekly.trim()?normalizedAmount(this.weekly):null;
    const monthly = this.monthly.trim() ? normalizedAmount(this.monthly) : null;
    const conceptos=this.draft.conceptos.map(row=>({...row,concepto:row.concepto.trim(),importe:normalizedAmount(row.importe)??''}));
    if((this.daily.trim()&&!diario)||(this.weekly.trim()&&!semanal)||(this.monthly.trim()&&!monthly)||conceptos.some(row=>!row.importe||!row.concepto||[...row.concepto].length>80)){
      this.error.set('Revisá los conceptos y los importes: usá valores positivos con hasta dos decimales.');return;
    }
    const datos:PlanData={limites:{diario:diario?{moneda:this.dailyCurrency,importe:diario}:null,semanal:semanal?{moneda:this.weeklyCurrency,importe:semanal}:null},conceptos};
    if (monthly || this.saved()!.datos.limites.mensual) {
      datos.limites.mensual = monthly ? { moneda: this.monthlyCurrency, importe: monthly } : null;
    }
    const categoryLimits = (this.draft.limites_categoria ?? [])
      .map(limit => ({ ...limit, importe: normalizedAmount(limit.importe) ?? '' }));
    if (categoryLimits.some(limit => !limit.importe)) {
      this.error.set('Ingresá un importe positivo para cada límite por categoría, con hasta dos decimales.');
      return;
    }
    if (categoryLimits.length || this.saved()!.datos.limites_categoria?.length) datos.limites_categoria = categoryLimits;
    const version=this.saved()!.version;const generation=this.generation;
    this.saving.set(true);this.error.set('');this.notice.set('');
    try{const result=await this.auth.accountRequest<PlanEnvelope>('POST',this.path,{version,datos});if(this.alive&&generation===this.generation){this.accept(result);this.notice.set('Presupuesto guardado. No se crearon gastos.');}}
    catch(error){if(this.alive&&generation===this.generation)this.error.set(error instanceof HttpErrorResponse&&error.status===409?'Otra sesión modificó el presupuesto. Tu borrador se conserva; recargá para revisar la versión guardada.':error instanceof HttpErrorResponse&&error.status===403?'No tenés permiso para modificar el presupuesto.':'No pudimos confirmar el guardado. Podés reintentar sin cambiar el borrador.');}
    finally{if(this.alive&&generation===this.generation)this.saving.set(false);}
  }
  add(){if(this.draft.conceptos.length>=40)return;this.draft.conceptos.push({id:crypto.randomUUID(),concepto:'',importe:'',moneda:'ARS',frecuencia:'semana'});this.dirty=true;}
  remove(id:string){if(!window.confirm('¿Quitar este concepto del presupuesto? No se borrarán gastos reales.'))return;this.draft.conceptos=this.draft.conceptos.filter(row=>row.id!==id);this.dirty=true;}
  show(){this.hidden.set(false);try{localStorage.setItem('gastos.totals.hidden','false');}catch{}window.dispatchEvent(new CustomEvent('gastos-privacy',{detail:false}));}
  readonly periods = ['diario', 'semanal', 'mensual'] as const;
  readonly money=money;
  limit(period: LimitPeriod){
    const limit=this.saved()?.datos.limites[period];if(!limit)return null;
    return limitUsage(limit,this.summary()?.totales,period,this.rate());
  }
  projection(period:'semana'|'mes') {return this.saved()?projected(this.saved()!.datos.conceptos,period,this.currency,this.rate()):null;}
  month(){const rows=this.summary()?.totales;return rows?reference(rows,'mes',this.currency,rateUnits(this.rate())):null;}
  comparison(){const planned=this.projection('mes'),spent=this.month();return planned!==null&&planned>0n&&spent!==null?progress(spent,planned):null;}
  distribution(){
    const total=this.projection('mes');if(total===null||total===0n)return [];
    return this.saved()!.datos.conceptos.map(row=>{const amount=projected([row],'mes',this.currency,this.rate())!;return {id:row.id,label:row.concepto,amount,...progress(amount,total)};});
  }
}
