import { Component, DestroyRef, Input, OnChanges, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AuthSession } from './auth-session';
import { CategoryCatalog } from './category-catalog';
import { cents, money } from './money-reference';

type Trend = { meses: string[]; items: { mes: string; moneda: string; categoria: string | null; total: string }[] };

@Component({
  selector: 'app-expense-trend',
  imports: [FormsModule],
  templateUrl: './expense-trend.html',
  styleUrl: './expense-trend.css',
})
export class ExpenseTrend implements OnChanges {
  @Input({ required: true }) space = '';
  @Input() account = '';
  @Input() revision = 0;
  readonly data = signal<Trend | null>(null);
  readonly failed = signal(false);
  readonly currency = signal('ARS');
  readonly category = signal('');
  readonly span = signal(6);
  private readonly catalog = inject(CategoryCatalog);
  get categories() { return this.catalog.expenseOptions(this.space); }
  readonly money = money;
  readonly chart = computed(() => {
    const data = this.data();
    if (!data) return [];
    const totals = new Map<string, bigint>();
    for (const item of data.items) {
      if (item.moneda !== this.currency() || (this.category() && this.category() !== (item.categoria ?? 'sin_categoria'))) continue;
      totals.set(item.mes, (totals.get(item.mes) ?? 0n) + cents(item.total));
    }
    const rows = data.meses.slice(-this.span()).map(month => ({ month, amount: totals.get(month) ?? 0n }));
    const max = rows.reduce((highest, row) => row.amount > highest ? row.amount : highest, 0n);
    return rows.map(row => ({ ...row, width: max ? Number(row.amount * 1000n / max) / 10 : 0 }));
  });
  private version = 0;
  private readonly auth = inject(AuthSession);

  constructor() { inject(DestroyRef).onDestroy(() => { this.version++; }); }
  ngOnChanges(): void { void this.load(); }

  async load(): Promise<void> {
    const version = ++this.version;
    this.data.set(null);
    this.failed.set(false);
    try {
      const query = this.account ? '?account=' + encodeURIComponent(this.account) : '';
      const result = await this.auth.accountRequest<Trend>(
        'GET', `/api/spaces/${encodeURIComponent(this.space)}/expense-trend${query}`,
      );
      if (this.version === version) this.data.set(result);
    } catch {
      if (this.version === version) this.failed.set(true);
    }
  }
}
