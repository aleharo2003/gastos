import { Component, DestroyRef, inject, input, OnInit, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AuthSession } from './auth-session';
import { showAmount } from './expenses';

type Movement = {
  id: string; fecha: string; tipo: 'gasto' | 'ingreso' | 'transferencia'; descripcion: string;
  moneda: string; importe: string; origen: string | null; destino: string | null;
};
type Totals = { moneda: string; ingresos: string; gastos: string; transferencias: string };
type Page = { items: Movement[]; totales: Totals[]; next_cursor: string | null };
const emptyFilters = { desde: '', hasta: '', tipo: '', moneda: '', cuenta: '', texto: '' };

@Component({
  selector: 'app-movements',
  imports: [FormsModule],
  templateUrl: './movements.html',
  styleUrl: './movements.css',
})
export class Movements implements OnInit {
  readonly space = input.required<string>();
  readonly accounts = input<readonly { id: string; nombre: string }[]>([]);
  readonly moreAccounts = input(false);
  readonly accountsLoading = input(false);
  readonly loadAccounts = output<void>();
  readonly amountsHidden = input(false);
  readonly items = signal<Movement[]>([]);
  readonly totals = signal<Totals[]>([]);
  readonly next = signal<string | null>(null);
  readonly loading = signal(false);
  readonly error = signal('');
  readonly loaded = signal(false);
  readonly labels = { gasto: 'Gasto', ingreso: 'Ingreso', transferencia: 'Transferencia' };
  filters = { ...emptyFilters };
  private applied = { ...emptyFilters };
  private request = 0;
  private readonly auth = inject(AuthSession);

  constructor() {
    inject(DestroyRef).onDestroy(() => { this.request++; });
  }

  ngOnInit(): void {
    void this.load();
  }

  datePreset(period: 'today' | 'month'): void {
    const today = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'America/Argentina/Buenos_Aires', year: 'numeric', month: '2-digit', day: '2-digit',
    }).format(new Date());
    this.filters.desde = period === 'month' ? today.slice(0, 7) + '-01' : today;
    this.filters.hasta = today;
    void this.load();
  }

  reset(): void {
    this.filters = { ...emptyFilters };
    void this.load();
  }

  amount(value: string): string {
    return this.amountsHidden() ? '••••' : showAmount(value);
  }

  async load(more = false): Promise<void> {
    if (this.loading() || (more && !this.next())) return;
    if (!more && this.filters.desde && this.filters.hasta && this.filters.desde > this.filters.hasta) {
      this.error.set('La fecha inicial debe ser anterior o igual a la fecha final.');
      return;
    }
    const filters = more ? this.applied : { ...this.filters };
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) if (value.trim()) params.set(key, value.trim());
    if (more) params.set('cursor', this.next()!);

    const version = ++this.request;
    this.loading.set(true);
    this.error.set('');
    try {
      const page = await this.auth.accountRequest<Page>(
        'GET', `/api/spaces/${encodeURIComponent(this.space())}/movements?${params}`,
      );
      if (version !== this.request) return;
      const rows = more ? [...this.items(), ...page.items] : page.items;
      this.items.set([...new Map(rows.map(row => [row.tipo + row.id, row])).values()]);
      this.totals.set(page.totales);
      this.next.set(page.next_cursor);
      this.applied = filters;
      this.loaded.set(true);
    } catch {
      if (version === this.request) this.error.set('No pudimos cargar los movimientos. Volvé a intentar.');
    } finally {
      if (version === this.request) this.loading.set(false);
    }
  }
}
