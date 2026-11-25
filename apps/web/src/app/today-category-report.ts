import { Component, DestroyRef, EventEmitter, Input, OnChanges, Output, inject, signal } from '@angular/core';
import { AuthSession } from './auth-session';
import { CategoryCatalog } from './category-catalog';
import { cents, money } from './money-reference';
import { progress } from './planning-math';

type Item = { moneda: string; categoria: string | null; total: string };

@Component({
  selector: 'app-today-category-report',
  templateUrl: './today-category-report.html',
})
export class TodayCategoryReport implements OnChanges {
  @Input({ required: true }) space = '';
  @Input() revision = 0;
  @Output() openExpenses = new EventEmitter<void>();
  @Output() openCategory = new EventEmitter<{ desde: string; hasta: string; categoria: string; moneda: string }>();
  private reportPeriod: { desde: string; hasta: string } | null = null;

  viewCategory(row: Item): void {
    if (!this.reportPeriod) return;
    this.openCategory.emit({ ...this.reportPeriod, categoria: row.categoria ?? 'sin_categoria', moneda: row.moneda });
  }

  readonly groups = signal<{ currency: string; total: bigint; items: Item[] }[] | null>(null);
  readonly failed = signal(false);
  readonly money = money;
  readonly cents = cents;
  private version = 0;
  private readonly auth = inject(AuthSession);
  private readonly catalog = inject(CategoryCatalog);

  constructor() { inject(DestroyRef).onDestroy(() => { this.version++; }); }
  ngOnChanges(): void { void this.load(); }

  label(category: string | null): string {
    return this.catalog.label(this.space, 'gasto', category);
  }

  share(amount: string, total: bigint): string {
    return total ? progress(cents(amount), total).text : '0,0%';
  }

  async load(): Promise<void> {
    const version = ++this.version;
    this.groups.set(null);
    this.reportPeriod = null;
    this.failed.set(false);
    try {
      const result = await this.auth.accountRequest<{ desde: string; hasta: string; items: Item[] }>(
        'GET', `/api/spaces/${encodeURIComponent(this.space)}/expense-category-summary`,
      );
      const groups = new Map<string, Item[]>();
      for (const row of result.items) {
        const rows = groups.get(row.moneda) ?? [];
        rows.push(row);
        groups.set(row.moneda, rows);
      }
      const summaries = [...groups].map(([currency, items]) => ({
        currency, items, total: items.reduce((sum, row) => sum + cents(row.total), 0n),
      }));
      if (version === this.version) {
        this.reportPeriod = { desde: result.desde, hasta: result.hasta };
        this.groups.set(summaries);
      }
    } catch {
      if (version === this.version) this.failed.set(true);
    }
  }
}
