import { Component, DestroyRef, inject, Input, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthSession } from './auth-session';

type Expense = { id: string; espacio_id: string; cuenta_id: string; fecha: string; descripcion: string; moneda: string; importe: string };
type Payload = Pick<Expense, 'id' | 'fecha' | 'descripcion' | 'moneda' | 'importe'>;
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
@Component({ selector: 'app-expenses', imports: [FormsModule], templateUrl: './expenses.html', styleUrl: './expenses.css' })
export class Expenses implements OnInit {
  @Input({ required: true }) space = '';
  @Input({ required: true }) account = { id: '', nombre: '' };
  readonly items = signal<Expense[]>([]);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly notice = signal('');
  readonly next = signal<number | null>(null);
  date = today(); description = ''; currency = 'ARS'; amount = '';
  readonly showAmount = showAmount;
  private readonly auth = inject(AuthSession);
  private alive = true;
  private pending?: Payload;
  constructor() { inject(DestroyRef).onDestroy(() => { this.alive = false; }); }
  ngOnInit() { void this.load(); }
  private get path() { return `/api/spaces/${encodeURIComponent(this.space)}/accounts/${encodeURIComponent(this.account.id)}/expenses`; }
  async load(more = false): Promise<void> {
    if (this.loading() || this.saving()) return;
    const offset = more ? this.next() : 0;
    if (offset === null) return;
    this.loading.set(true); this.error.set('');
    try {
      const page = await this.auth.accountRequest<{items: Expense[]; next_offset: number|null}>('GET', `${this.path}?offset=${offset}`);
      if (!this.alive) return;
      const rows = more ? [...this.items(), ...page.items] : page.items;
      this.items.set([...new Map(rows.map(row => [row.id, row])).values()]);
      this.next.set(page.next_offset);
    } catch { if (this.alive) this.error.set('No pudimos cargar los gastos. Volvé a intentar.'); }
    finally { if (this.alive) this.loading.set(false); }
  }
  async save(): Promise<void> {
    if (this.saving() || this.loading()) return;
    const amount = normalizeAmount(this.amount), description = this.description.trim();
    this.error.set(''); this.notice.set('');
    if (!amount) { this.error.set('Ingresá un importe mayor que cero, sin separador de miles y con hasta dos decimales.'); return; }
    if (!description || [...description].length > 160 || !this.date || !['ARS','USD','EUR'].includes(this.currency)) return;
    const values = {fecha: this.date, descripcion: description, moneda: this.currency, importe: amount};
    if (!this.pending || Object.entries(values).some(([key,value]) => this.pending![key as keyof Payload] !== value)) this.pending = { id: crypto.randomUUID(), ...values };
    this.saving.set(true);
    try {
      const row = await this.auth.accountRequest<Expense>('POST', this.path, this.pending);
      if (!this.alive) return;
      this.items.update(items => [row, ...items.filter(item => item.id !== row.id)].sort((a,b) => b.fecha.localeCompare(a.fecha) || b.id.localeCompare(a.id)));
      this.pending = undefined; this.description = ''; this.amount = '';
      this.notice.set('Gasto guardado.');
    } catch (error) {
      if (this.alive) this.error.set(error instanceof HttpErrorResponse && error.status === 403
        ? 'No tenés permiso para registrar gastos en este espacio.'
        : 'No pudimos confirmar el guardado. Reintentá sin cambiar los datos para evitar duplicar esta solicitud.');
    } finally { if (this.alive) this.saving.set(false); }
  }
}
