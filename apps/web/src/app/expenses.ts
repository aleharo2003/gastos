import { Component, DestroyRef, inject, Input, OnInit, signal, ViewChildren, QueryList } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthSession } from './auth-session';
import { ExpenseTotals } from './expense-totals';
import { Receipts } from './receipts';
import { SimilarExpenses } from './similar-expenses';

type Expense = { id: string; espacio_id: string; cuenta_id: string; fecha: string; descripcion: string; moneda: string; importe: string; categoria?: string | null; coincidencia_aproximada?: boolean; cuenta_nombre?: string };
type CategorySuggestion = {categoria:string|null;coincidencias:number;total:number};
type Payload = Pick<Expense, 'id' | 'fecha' | 'descripcion' | 'moneda' | 'importe' | 'categoria'>;
export function normalizeAmount(value: string): string | null {
  const text = value.trim().replace(',', '.');
  if (!/^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?$/.test(text) || !/[1-9]/.test(text)) return null;
  const [whole, fraction = ''] = text.split('.');
  return whole + '.' + fraction.padEnd(2, '0');
}
export function showAmount(value: string): string {
  const [whole, fraction] = value.split('.');
  return whole.replace(/\B(?=(\d{3})+(?!\d))/g, '.') + ',' + fraction;
}
function today() {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
}
@Component({ selector: 'app-expenses', imports: [FormsModule, Receipts, SimilarExpenses, ExpenseTotals], templateUrl: './expenses.html', styleUrl: './expenses.css' })
export class Expenses implements OnInit {
  @Input({ required: true }) space = '';
  @Input({ required: true }) account = { id: '', nombre: '' };
  @Input() accounts: {id:string;nombre:string}[] = [];
  createAccount = '';
  editAccount = '';
  private savedAccount = '';
  readonly summaryRevision = signal(0);
  readonly items = signal<Expense[]>([]);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly notice = signal('');
  readonly next = signal<number | null>(null);
  readonly categories = [
    {id:'alimentos',label:'Alimentos'}, {id:'transporte',label:'Transporte'},
    {id:'vivienda',label:'Vivienda'}, {id:'servicios',label:'Servicios'},
    {id:'salud',label:'Salud'}, {id:'educacion',label:'Educación'},
    {id:'ocio',label:'Ocio'}, {id:'impuestos',label:'Impuestos'},
    {id:'auto',label:'Auto'}, {id:'bancario',label:'Bancario'},
    {id:'ropa',label:'Ropa'}, {id:'otros',label:'Otros'},
  ];
  category = '';
  readonly suggestion = signal<CategorySuggestion|null>(null);
  readonly suggesting = signal(false);
  readonly suggestionNote = signal('');
  private suggestionVersion = 0;
  clearSuggestion() {
    this.suggestionVersion++; this.suggestion.set(null); this.suggesting.set(false); this.suggestionNote.set('');
  }
  async requestSuggestion() {
    this.clearSuggestion();
    const description=this.description.trim();
    if(!(this.account.id || this.createAccount) || this.editing || this.category || this.saving() || [...description].length<4 || [...description].length>160)return;
    const version=this.suggestionVersion;
    this.suggesting.set(true);
    const current=()=>this.alive && version===this.suggestionVersion && !this.editing && !this.category && !this.saving() && this.description.trim()===description;
    try {
      const result=await this.auth.accountRequest<CategorySuggestion>('GET',`${this.writePath}/category-suggestion?${new URLSearchParams({descripcion:description})}`);
      if(!current())return;
      if(result.categoria && this.categories.some(c=>c.id===result.categoria))this.suggestion.set(result);
      else this.suggestionNote.set('Todavía no hay antecedentes suficientes y consistentes en esta cuenta. Podés elegir la categoría.');
    } catch {
      if(current())this.suggestionNote.set('No pudimos buscar una sugerencia. Podés elegir la categoría y guardar igual.');
    } finally {if(this.alive && version===this.suggestionVersion)this.suggesting.set(false);}
  }
  applySuggestion() {
    const value=this.suggestion();
    if(!value?.categoria || this.category || this.editing || this.saving())return;
    this.category=value.categoria; this.clearSuggestion();
  }
  filterApproximate = true;
  filterFrom = ''; filterTo = ''; filterCategory = ''; filterCurrency = ''; filterText = '';
  readonly appliedFilters = signal('');
  categoryName(id?:string|null) { return this.categories.find(c=>c.id===id)?.label ?? 'Sin categoría'; }
  receiptOutsideList() { return !!this.receiptExpense() && !this.items().some(r=>r.id===this.receiptExpense()); }
  async applyFilters(clear = false) {
    if(this.loading() || this.saving())return;
    if(clear){this.filterApproximate=true;this.filterFrom='';this.filterTo='';this.filterCategory='';this.filterCurrency='';this.filterText='';}
    if(this.filterFrom && this.filterTo && this.filterFrom>this.filterTo){this.error.set('La fecha Desde no puede ser posterior a Hasta.');return;}
    const params=new URLSearchParams();
    for(const [key,value] of Object.entries({desde:this.filterFrom,hasta:this.filterTo,categoria:this.filterCategory,moneda:this.filterCurrency,texto:this.filterText.trim()})) {
      if(value)params.set(key,value);
    }
    if(this.filterText.trim())params.set('aproximada',String(this.filterApproximate));
    this.appliedFilters.set(params.toString()); this.next.set(null); this.items.set([]);
    await this.load();
  }
  date = today(); description = ''; currency = 'ARS'; amount = '';
  readonly showAmount = showAmount;
  private readonly auth = inject(AuthSession);
  private alive = true;
  private pending?: Payload;
  readonly similarExpense=signal<string|null>(null);
  similarPath(id:string){return `${this.itemPath(id)}/${id}/similar`;}
  toggleSimilar(id:string){if(!this.loading() && !this.saving())this.similarExpense.set(this.similarExpense()===id?null:id);}
  readonly receiptExpense=signal<string|null>(null);
  readonly lastSaved=signal<string|null>(null);
  receiptPath(id:string){return `${this.itemPath(id)}/${id}/receipts`;}
  openReceipts(id:string|null){
    this.receiptExpense.set(id);
    if(id)setTimeout(()=>{if(this.alive)document.getElementById('receipts-'+id)?.scrollIntoView({block:'nearest'});});
  }
  @ViewChildren(Receipts) receiptPanels!: QueryList<Receipts>;
  editorOpen = false;
  hasPendingWork(): boolean {
    return this.saving() || !!(this.editing || this.description || this.amount || this.category)
      || !!this.receiptPanels?.some(panel => panel.busy() || !!panel.selected());
  }
  editing: Payload | null = null;
  edit(item: Expense): void {
    if (this.saving() || this.loading()) return;
    if ((this.editing || this.description || this.amount) && !window.confirm('¿Descartar el formulario actual y editar este gasto?')) return;
    this.clearSuggestion();
    this.editorOpen = true;
    this.similarExpense.set(null);
    this.editAccount = item.cuenta_id;
    this.editing = {id:item.id,fecha:item.fecha,descripcion:item.descripcion,moneda:item.moneda,importe:item.importe,categoria:item.categoria ?? null};
    this.category=item.categoria ?? ''; this.date=item.fecha; this.description=item.descripcion; this.currency=item.moneda; this.amount=item.importe;
    this.pending=undefined; this.error.set(''); this.notice.set('Editando el gasto seleccionado.');
    setTimeout(() => { if (this.alive) document.getElementById('expense-date')?.focus(); });
  }
  cancelEdit(): void {
    if (this.saving() || !window.confirm('¿Descartar los cambios de este gasto?')) return;
    this.clearSuggestion();
    this.editing=null; this.category=''; this.date=today(); this.description=''; this.amount=''; this.error.set(''); this.notice.set('Edición cancelada.');
  }
  constructor() { inject(DestroyRef).onDestroy(() => { this.alive = false; }); }
  ngOnInit() { void this.load(); }
  private accountPath(id:string) { return `/api/spaces/${encodeURIComponent(this.space)}/accounts/${encodeURIComponent(id)}/expenses`; }
  private get path() { return this.account.id ? this.accountPath(this.account.id) : `/api/spaces/${encodeURIComponent(this.space)}/expenses`; }
  private get writePath() { return this.accountPath(this.editing ? this.editAccount : this.account.id || this.createAccount); }
  private itemPath(id:string) { return this.accountPath(this.items().find(row=>row.id===id)?.cuenta_id ?? (this.lastSaved()===id ? this.savedAccount : this.account.id)); }
  accountName(id:string) { return this.accounts.find(row=>row.id===id)?.nombre ?? this.items().find(row=>row.cuenta_id===id)?.cuenta_nombre ?? (this.account.id===id ? this.account.nombre : 'Cuenta'); }
  changeCreateAccount() { this.clearSuggestion(); this.pending=undefined; }

  async load(more = false): Promise<void> {
    if (this.loading() || this.saving()) return;
    const offset = more ? this.next() : 0;
    if (offset === null) return;
    if(!more)this.similarExpense.set(null);
    if(!more)this.summaryRevision.update(n=>n+1);
    this.loading.set(true); this.error.set('');
    try {
      const page = await this.auth.accountRequest<{items: Expense[]; next_offset: number|null}>('GET', `${this.path}?offset=${offset}${this.appliedFilters() ? '&' + this.appliedFilters() : ''}`);
      if (!this.alive) return;
      const rows = more ? [...this.items(), ...page.items] : page.items;
      this.items.set([...new Map(rows.map(row => [row.id, row])).values()]);
      this.next.set(page.next_offset);
    } catch { if (this.alive) this.error.set('No pudimos cargar los gastos. Volvé a intentar.'); }
    finally { if (this.alive) this.loading.set(false); }
  }
  async save(): Promise<void> {
    if (this.saving() || this.loading()) return;
    if (!(this.editing ? this.editAccount : this.account.id || this.createAccount)) { this.error.set('Elegí la cuenta del gasto.'); return; }
    const amount = normalizeAmount(this.amount), description = this.description.trim();
    this.error.set(''); this.notice.set('');
    if (!amount) { this.error.set('Ingresá un importe mayor que cero, sin separador de miles y con hasta dos decimales.'); return; }
    if (!description || [...description].length > 160 || !this.date || !['ARS','USD','EUR'].includes(this.currency)) return;
    const values = {fecha: this.date, descripcion: description, moneda: this.currency, importe: amount, categoria: this.category || null};
    if (!this.pending || Object.entries(values).some(([key,value]) => this.pending![key as keyof Payload] !== value)) this.pending = { id: crypto.randomUUID(), ...values };
    this.clearSuggestion();
    this.saving.set(true);
    let saved = false;
    try {
      const editing = this.editing;
      const row = editing
        ? await this.auth.accountRequest<Expense>('PATCH', `${this.writePath}/${editing.id}`, {original:editing,nuevo:{id:editing.id,...values}})
        : await this.auth.accountRequest<Expense>('POST', this.writePath, this.pending);
      if (!this.alive) return;
      this.items.update(items => [row, ...items.filter(item => item.id !== row.id)].sort((a,b) => b.fecha.localeCompare(a.fecha) || b.id.localeCompare(a.id)));
      this.pending = undefined; this.description = ''; this.amount = '';
      this.clearSuggestion();
      this.editing=null; this.category=''; this.date=today();
      this.notice.set(editing ? 'Cambios guardados.' : 'Gasto guardado.');
      saved = true;
      this.similarExpense.set(null);
      this.lastSaved.set(row.id); this.savedAccount=row.cuenta_id;
      this.summaryRevision.update(n=>n+1);
      if(this.appliedFilters()){this.notice.set('Guardado. La lista respeta los filtros; el gasto puede quedar fuera de los resultados.');}
    } catch (error) {
      if (this.alive) this.error.set(error instanceof HttpErrorResponse && error.status === 409 && this.editing
        ? 'El gasto cambió desde otra sesión. Tu formulario se conserva. Actualizá la lista y volvé a seleccionar Editar para revisar los valores actuales.'
        : error instanceof HttpErrorResponse && error.status === 403
        ? 'No tenés permiso para registrar gastos en este espacio.'
        : 'No pudimos confirmar el guardado. Reintentá sin cambiar los datos para evitar duplicar esta solicitud.');
    } finally { if (this.alive) this.saving.set(false); }
    if(saved && this.alive && this.appliedFilters()) {
      this.items.set([]); this.next.set(null); await this.load();
    }
  }
}
