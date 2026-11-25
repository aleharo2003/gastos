import { Component, DestroyRef, inject, input, OnInit, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { EXPENSE_CATEGORIES } from './expense-categories';
import { AuthSession } from './auth-session';
import { movementCsv } from './movement-csv';
import { showAmount } from './expenses';

type Movement = {
  id: string; fecha: string; tipo: 'gasto' | 'ingreso' | 'transferencia'; descripcion: string;
  moneda: string; importe: string; origen: string | null; destino: string | null; categoria?: string | null;
};
type Totals = { moneda: string; ingresos: string; gastos: string; transferencias: string; variacion_cuenta?: string };
type Page = { items: Movement[]; totales: Totals[]; next_cursor: string | null };
const emptyFilters = { desde: '', hasta: '', tipo: '', moneda: '', cuenta: '', texto: '', categoria: '' };

@Component({
  selector: 'app-movements',
  imports: [FormsModule],
  templateUrl: './movements.html',
  styleUrl: './movements.css',
})
export class Movements implements OnInit {
  readonly space = input.required<string>();
  readonly initialReport = input<{ desde: string; hasta: string; categoria: string; moneda: string } | null>(null);
  readonly initialAccount = input<{ id: string; nombre: string } | null>(null);
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
  readonly exporting = signal(false);
  readonly exportError = signal('');
  readonly loaded = signal(false);
  readonly categories = EXPENSE_CATEGORIES;
  readonly labels = { gasto: 'Gasto', ingreso: 'Ingreso', transferencia: 'Transferencia' };
  filters = { ...emptyFilters };
  private applied = { ...emptyFilters };
  private request = 0;
  private readonly auth = inject(AuthSession);

  constructor() {
    inject(DestroyRef).onDestroy(() => { this.request++; });
  }

  accountAvailable(id: string): boolean {
    return this.accounts().some(account => account.id === id);
  }

  categoryName(category?: string | null): string {
    return this.categories.find(item => item.id === category)?.label ?? 'Sin categoría';
  }

  ngOnInit(): void {
    this.filters.cuenta = this.initialAccount()?.id ?? '';
    const report = this.initialReport();
    if (report) Object.assign(this.filters, report, { tipo: 'gasto' });
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

  net(ingresos: string, gastos: string): string {
    const value = BigInt(ingresos.replace('.', '')) - BigInt(gastos.replace('.', ''));
    const digits = (value < 0n ? -value : value).toString().padStart(3, '0');
    return this.amount((value < 0n ? '-' : '') + digits.slice(0, -2) + '.' + digits.slice(-2));
  }

  amount(value: string): string {
    return this.amountsHidden() ? '••••' : showAmount(value);
  }

  async exportCsv(): Promise<void> {
    if (this.exporting() || this.loading() || this.amountsHidden() || !this.loaded()) return;
    const request = this.request;
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(this.applied)) if (value.trim()) params.set(key, value.trim());
    this.exporting.set(true);
    this.exportError.set('');
    try {
      const rows = new Map<string, Movement>();
      const seen = new Set<string>();
      let cursor: string | null = null;
      do {
        if (cursor) params.set('cursor', cursor);
        const page: Page = await this.auth.accountRequest<Page>(
          'GET', `/api/spaces/${encodeURIComponent(this.space())}/movements?${params}`,
        );
        if (request !== this.request || this.amountsHidden()) return;
        for (const row of page.items) rows.set(row.tipo + row.id, row);
        cursor = page.next_cursor;
        if (cursor && seen.has(cursor)) throw new Error('Cursor repetido');
        if (cursor) seen.add(cursor);
      } while (cursor);

      const url = URL.createObjectURL(new Blob([movementCsv([...rows.values()])], { type: 'text/csv;charset=utf-8' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = 'piggo-movimientos.csv';
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      if (request === this.request) this.exportError.set('No pudimos exportar los movimientos.');
    } finally {
      this.exporting.set(false);
    }
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
