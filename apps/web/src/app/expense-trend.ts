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
  readonly selectedCategories = signal<string[]>([]);
  readonly from = signal('');
  readonly to = signal('');
  readonly months = computed(() => this.data()?.meses ?? []);
  readonly end = computed(() => this.to() || this.months().at(-1) || '');
  readonly start = computed(() => {
    const start = this.from() || this.months().at(-6) || '';
    return start > this.end() ? this.end() : start;
  });
  private readonly catalog = inject(CategoryCatalog);
  get categories() { return this.catalog.expenseOptions(this.space); }
  readonly money = money;
  readonly chart = computed(() => {
    const data = this.data();
    if (!data) return [];
    const categories = this.selectedCategories();
    const totals = new Map<string, bigint>();
    for (const item of data.items) {
      if (item.moneda !== this.currency() ||
          (categories.length && !categories.includes(item.categoria ?? 'sin_categoria'))) continue;
      totals.set(item.mes, (totals.get(item.mes) ?? 0n) + cents(item.total));
    }
    const start = this.start();
    const end = this.end();
    const rows = data.meses.filter(month => month >= start && month <= end)
      .map(month => ({ month, amount: totals.get(month) ?? 0n }));
    const max = rows.reduce((highest, row) => row.amount > highest ? row.amount : highest, 0n);
    return rows.map(row => ({ ...row, width: max ? Number(row.amount * 1000n / max) / 10 : 0 }));
  });
  private version = 0;
  private readonly auth = inject(AuthSession);

  constructor() { inject(DestroyRef).onDestroy(() => { this.version++; }); }
  ngOnChanges(): void { void this.load(); }

  toggleCategory(category: string, selected: boolean): void {
    this.selectedCategories.update(items => selected ? [...items, category] : items.filter(item => item !== category));
  }

  setStart(month: string): void {
    if (month > this.end()) this.to.set(month);
    this.from.set(month);
  }

  setEnd(month: string): void {
    if (month < this.start()) this.from.set(month);
    this.to.set(month);
  }

  async load(): Promise<void> {
    const version = ++this.version;
    this.data.set(null);
    this.failed.set(false);
    try {
      const query = this.account ? '?account=' + encodeURIComponent(this.account) : '';
      const result = await this.auth.accountRequest<Trend>(
        'GET', `/api/spaces/${encodeURIComponent(this.space)}/expense-trend${query}`,
      );
      if (this.version === version) {
        if (!result.meses.includes(this.from())) this.from.set('');
        if (!result.meses.includes(this.to())) this.to.set('');
        this.data.set(result);
      }
    } catch {
      if (this.version === version) this.failed.set(true);
    }
  }
}
