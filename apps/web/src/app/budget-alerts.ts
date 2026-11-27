import { Component, DestroyRef, inject, input, OnChanges, signal, SimpleChanges } from '@angular/core';
import { AuthSession } from './auth-session';
import { CategoryCatalog } from './category-catalog';
import { cents, money } from './money-reference';

type BudgetAlert = {
  id: string;
  periodo: 'diario' | 'semanal' | 'mensual';
  desde: string;
  categoria: string;
  moneda: 'ARS' | 'USD';
  exceso: string;
};

type Alerts = { items: BudgetAlert[] };

@Component({
  selector: 'app-budget-alerts',
  template: `
    @if (items().length && !hiddenAmounts()) {
      <section class="workspace-panel planning-panel" aria-labelledby="budget-alert-title">
        <h3 id="budget-alert-title">Avisos de presupuesto</h3>
        <ul>
          @for (row of items(); track row.id) {
            <li>
              <p role="status">{{ label(row) }} · Superaste el límite por {{ row.moneda }} {{ amount(row.exceso) }}.
                <small>Período desde {{ row.desde.split('-').reverse().join('/') }}</small></p>
              <button type="button" class="secondary" (click)="dismiss(row.id)" [disabled]="dismissing()"
                [attr.aria-label]="'Entendido: ' + label(row)">Entendido</button>
            </li>
          }
        </ul>
        @if (error()) { <p role="alert">{{ error() }}</p> }
      </section>
    }
  `,
})
export class BudgetAlerts implements OnChanges {
  readonly space = input.required<string>();
  readonly revision = input(0);
  readonly hiddenAmounts = input(false);
  readonly items = signal<BudgetAlert[]>([]);
  readonly dismissing = signal(false);
  readonly error = signal('');
  readonly amount = (value: string) => money(cents(value));
  private readonly auth = inject(AuthSession);
  private readonly catalog = inject(CategoryCatalog);
  private readonly destroy = inject(DestroyRef);
  private request = 0;

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['space']) {
      this.items.set([]);
      this.error.set('');
    }
    if (changes['space'] || changes['revision']) void this.load();
  }

  label(row: BudgetAlert): string {
    return row.categoria ? this.catalog.label(this.space(), 'gasto', row.categoria) : 'Límite ' + row.periodo;
  }

  private get path(): string {
    return `/api/spaces/${encodeURIComponent(this.space())}/spending-plan/alerts`;
  }

  private async load(): Promise<void> {
    const request = ++this.request;
    try {
      const result = await this.auth.accountRequest<Alerts>('GET', this.path);
      if (!this.destroy.destroyed && request === this.request) this.items.set(Array.isArray(result?.items) ? result.items : []);
    } catch {
      if (!this.destroy.destroyed && request === this.request) this.items.set([]);
    }
  }

  async dismiss(id: string): Promise<void> {
    if (this.dismissing()) return;
    const space = this.space();
    this.dismissing.set(true);
    this.error.set('');
    try {
      await this.auth.accountRequest<Alerts>('POST', this.path, { id });
      if (!this.destroy.destroyed && this.space() === space) {
        this.items.update(items => items.filter(row => row.id !== id));
        await this.load();
      }
    } catch {
      if (!this.destroy.destroyed && this.space() === space) this.error.set('No pudimos cerrar el aviso. Volvé a intentar.');
    } finally {
      if (!this.destroy.destroyed) this.dismissing.set(false);
    }
  }
}
