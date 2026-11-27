import { Component, DestroyRef, effect, ElementRef, inject, input, OnInit, output, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CategoryCatalog, CategoryKind } from './category-catalog';
import { AuthSession } from './auth-session';
import { movementCsv } from './movement-csv';
import { showAmount } from './expenses';

type Movement = {
  id: string; fecha: string; tipo: 'gasto' | 'ingreso' | 'transferencia' | 'cambio'; descripcion: string;
  moneda: string; importe: string; origen: string | null; destino: string | null; categoria?: string | null; anulado?: boolean;
  moneda_destino?: string; importe_destino?: string;
};
type Totals = { moneda: string; ingresos: string; gastos: string; transferencias: string; variacion_cuenta?: string;
  cambio_entrada?: string; cambio_salida?: string };
type Page = { items: Movement[]; totales: Totals[]; next_cursor: string | null };
const emptyFilters = { desde: '', hasta: '', tipo: '', moneda: '', cuenta: '', texto: '', categoria: '', anulados: '' };

function filterParams(filters: typeof emptyFilters): URLSearchParams {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value.trim()) params.set(key, value.trim());
  }
  const category = params.get('categoria');
  if (category?.startsWith('ingreso:')) {
    params.delete('categoria');
    params.set('categoria_ingreso', category.slice('ingreso:'.length));
  }
  return params;
}

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
  readonly inactiveChoices = signal<{ id: string; nombre: string }[]>([]);
  readonly inactiveLoading = signal(false);
  readonly inactiveError = signal(false);
  readonly nextInactive = signal<number | null>(0);

  async loadInactiveChoices(): Promise<void> {
    const offset = this.nextInactive();
    if (offset === null || this.inactiveLoading()) return;
    const space = this.space();
    this.inactiveLoading.set(true);
    this.inactiveError.set(false);
    try {
      const page = await this.auth.accountRequest<{ items: { id: string; nombre: string }[]; next_offset: number | null }>(
        'GET', `/api/spaces/${encodeURIComponent(space)}/accounts?offset=${offset}&inactivas=true`,
      );
      this.inactiveChoices.update(rows => [...new Map([...rows, ...page.items].map(row => [row.id, row])).values()]);
      this.nextInactive.set(page.next_offset);
    } catch {
      this.inactiveError.set(true);
    } finally {
      this.inactiveLoading.set(false);
    }
  }
  readonly accountsLoading = input(false);
  readonly loadAccounts = output<void>();
  readonly changed = output<void>();
  readonly amountsHidden = input(false);
  readonly items = signal<Movement[]>([]);
  readonly totals = signal<Totals[]>([]);
  readonly next = signal<string | null>(null);
  private readonly moreButton = viewChild<ElementRef<HTMLButtonElement>>('moreMovements');
  readonly loading = signal(false);
  readonly error = signal('');
  readonly voiding = signal(false);
  readonly voidNotice = signal('');
  readonly voidError = signal('');
  readonly exporting = signal(false);
  readonly exportError = signal('');
  readonly exportedRows = signal(0);
  private exportVersion = 0;

  cancelExport(): void {
    this.exportVersion++;
    this.exporting.set(false);
  }
  readonly loaded = signal(false);
  private readonly catalog = inject(CategoryCatalog);
  get categories() { return this.catalog.expenseOptions(this.space()); }
  get incomeCategories() { return this.catalog.categories(this.space(), 'ingreso'); }
  readonly labels = { gasto: 'Gasto', ingreso: 'Ingreso', transferencia: 'Transferencia', cambio: 'Cambio' };
  movementLabel(row: Movement): string {
    if (row.tipo === 'cambio') return row.moneda === 'ARS' ? 'Compra de USD' : 'Venta de USD';
    return this.labels[row.tipo];
  }

  filters = { ...emptyFilters };
  private applied = { ...emptyFilters };
  private request = 0;
  private readonly auth = inject(AuthSession);
  private readonly destroy = inject(DestroyRef);

  constructor() {
    this.destroy.onDestroy(() => { this.request++; });
    effect(onCleanup => {
      const button = this.moreButton()?.nativeElement;
      const cursor = this.next();
      if (!button || !cursor || typeof IntersectionObserver === 'undefined') return;
      const observer = new IntersectionObserver(entries => {
        if (!this.destroy.destroyed && entries.some(entry => entry.isIntersecting) && this.next() === cursor &&
            !this.error() && !this.exporting() && !this.voiding()) void this.load(true);
      });
      observer.observe(button);
      onCleanup(() => observer.disconnect());
    });
  }

  accountAvailable(id: string): boolean {
    return [...this.accounts(), ...this.inactiveChoices()].some(account => account.id === id);
  }

  categoryName(category?: string | null, type: CategoryKind = 'gasto'): string {
    return this.catalog.label(this.space(), type, category);
  }

  ngOnInit(): void {
    const account = this.initialAccount();
    const report = this.initialReport();
    if (account) this.filters.cuenta = account.id;
    if (report) Object.assign(this.filters, report, { tipo: 'gasto' });
    if (!account && !report) this.restoreFilters();
    void this.load(false, false);
  }

  private filterStorageKey(): string | undefined {
    const userId = this.auth.userId;
    if (userId) return `piggo:movement-filters:${userId}:${this.space()}`;
    return undefined;
  }

  private restoreFilters(): void {
    const key = this.filterStorageKey();
    if (!key) return;
    try {
      const saved: unknown = JSON.parse(localStorage.getItem(key) ?? 'null');
      if (!saved || typeof saved !== 'object') return;
      const values = saved as Record<string, unknown>;
      for (const field of Object.keys(emptyFilters) as (keyof typeof emptyFilters)[]) {
        const value = values[field];
        if (typeof value === 'string') this.filters[field] = value;
      }
    } catch {
      // The history remains available when browser storage is disabled or damaged.
    }
  }

  private rememberFilters(filters: typeof emptyFilters): void {
    const key = this.filterStorageKey();
    if (!key) return;
    try {
      localStorage.setItem(key, JSON.stringify(filters));
    } catch {
      // Applying a filter does not require browser storage.
    }
  }

  datePreset(period: 'today' | 'month' | 'previous'): void {
    const today = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'America/Argentina/Buenos_Aires', year: 'numeric', month: '2-digit', day: '2-digit',
    }).format(new Date());
    if (period === 'previous') {
      const first = new Date(today.slice(0, 7) + '-01T00:00:00Z');
      first.setUTCDate(0);
      const last = first.toISOString().slice(0, 10);
      this.filters.desde = last.slice(0, 7) + '-01';
      this.filters.hasta = last;
      void this.load();
      return;
    }
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
    if (this.exporting() || this.loading() || this.voiding() || this.amountsHidden() || !this.loaded()) return;
    const request = this.request;
    const exportVersion = ++this.exportVersion;
    this.exportedRows.set(0);
    const params = filterParams(this.applied);
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
        if (request !== this.request || exportVersion !== this.exportVersion || this.amountsHidden()) return;
        for (const row of page.items) rows.set(row.tipo + row.id, row);
        this.exportedRows.set(rows.size);
        cursor = page.next_cursor;
        if (cursor && seen.has(cursor)) throw new Error('Cursor repetido');
        if (cursor) seen.add(cursor);
      } while (cursor);

      const url = URL.createObjectURL(new Blob([movementCsv([...rows.values()], (id, type) => this.categoryName(id, type))],
        { type: 'text/csv;charset=utf-8' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = 'piggo-movimientos.csv';
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      if (request === this.request && exportVersion === this.exportVersion) this.exportError.set('No pudimos exportar los movimientos.');
    } finally {
      if (exportVersion === this.exportVersion) this.exporting.set(false);
    }
  }

  async confirmVoid(row: Movement): Promise<void> {
    if (this.loading() || this.voiding() || this.exporting() || row.anulado || (row.tipo !== 'ingreso' && row.tipo !== 'transferencia')) return;
    const label = row.tipo === 'ingreso' ? 'el ingreso' : 'la transferencia';
    if (!window.confirm(`¿Anular ${label} «${row.descripcion}»? Los saldos se actualizarán y el movimiento quedará en Anulados.`)) return;
    this.voiding.set(true);
    this.voidNotice.set('');
    this.voidError.set('');
    try {
      const path = `/api/spaces/${encodeURIComponent(this.space())}/movements/${row.tipo}/${encodeURIComponent(row.id)}/void`;
      await this.auth.accountRequest('POST', path);
    } catch {
      if (!this.destroy.destroyed) this.voidError.set('No pudimos anular el movimiento. Volvé a intentar.');
      return;
    } finally {
      if (!this.destroy.destroyed) this.voiding.set(false);
    }
    if (this.destroy.destroyed) return;
    this.items.update(rows => rows.filter(item => item.id !== row.id || item.tipo !== row.tipo));
    this.totals.set([]);
    this.next.set(null);
    this.voidNotice.set(row.tipo === 'ingreso' ? 'Ingreso anulado.' : 'Transferencia anulada.');
    this.changed.emit();
    await this.load(false, false, this.applied);
  }

  async load(more = false, remember = true, selectedFilters = this.filters): Promise<void> {
    const cursor = more ? this.next() : null;
    if (this.voiding() || this.loading() || (more && (!cursor || this.exporting()))) return;
    if (!more && selectedFilters.desde && selectedFilters.hasta && selectedFilters.desde > selectedFilters.hasta) {
      this.error.set('La fecha inicial debe ser anterior o igual a la fecha final.');
      return;
    }
    const filters = more ? this.applied : { ...selectedFilters };
    const params = filterParams(filters);
    if (cursor) params.set('cursor', cursor);

    const version = ++this.request;
    this.loading.set(true);
    this.error.set('');
    try {
      const page = await this.auth.accountRequest<Page>(
        'GET', `/api/spaces/${encodeURIComponent(this.space())}/movements?${params}`,
      );
      if (version !== this.request) return;
      if (cursor && page.next_cursor === cursor) throw new Error('Cursor repetido');
      const rows = more ? [...this.items(), ...page.items] : page.items;
      this.items.set([...new Map(rows.map(row => [row.tipo + row.id, row])).values()]);
      this.totals.set(page.totales);
      this.next.set(page.next_cursor);
      this.applied = filters;
      if (!more && remember) this.rememberFilters(filters);
      this.loaded.set(true);
    } catch {
      if (version === this.request) this.error.set('No pudimos cargar los movimientos. Volvé a intentar.');
    } finally {
      if (version === this.request) this.loading.set(false);
    }
  }
}
