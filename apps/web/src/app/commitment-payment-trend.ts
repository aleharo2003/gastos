import { Component, DestroyRef, Input, OnChanges, computed, inject, signal } from '@angular/core';
import { AuthSession } from './auth-session';
import { cents, money } from './money-reference';

type PaymentTrend = { items: { mes: string; total: string }[] };

@Component({
  selector: 'app-commitment-payment-trend',
  template: `
    @if (hidden) {
      <p>Importes ocultos.</p>
    } @else if (failed()) {
      <p role="alert">No pudimos cargar los pagos por mes.</p>
      <button type="button" class="secondary" (click)="load()">Reintentar</button>
    } @else if (rows(); as periods) {
      @if (variation(); as change) {
        <p>Variación acumulada entre {{ change.first }} y {{ change.last }}:
          <strong>{{ change.percent }} %</strong>
        </p>
      }
      @if (periods.some(hasPayment)) {
        <p>Últimos 12 meses, agrupados por fecha de pago.</p>
        <ul class="trend-chart" aria-label="Pagos por mes">
          @for (period of periods; track period.month) {
            <li>
              <span>{{ period.month }}</span>
              <span class="trend-track" aria-hidden="true"><span [style.width.%]="period.width"></span></span>
              <strong>{{ currency }} {{ money(period.amount) }}</strong>
            </li>
          }
        </ul>
      } @else {
        <p>No hay pagos registrados en los últimos 12 meses.</p>
      }
    } @else {
      <p role="status">Cargando pagos por mes.</p>
    }
  `,
  styleUrl: './expense-trend.css',
})
export class CommitmentPaymentTrend implements OnChanges {
  @Input({ required: true }) space = '';
  @Input({ required: true }) commitment = '';
  @Input({ required: true }) currency = '';
  @Input() totalPaid = '';
  @Input() hidden = false;

  private readonly auth = inject(AuthSession);
  private version = 0;
  private readonly data = signal<PaymentTrend | null>(null);
  readonly failed = signal(false);
  readonly money = money;
  readonly hasPayment = (row: { amount: bigint }) => row.amount > 0n;
  readonly rows = computed(() => {
    const data = this.data();
    if (!data) return null;
    const rows = data.items.map(({ mes, total }) => ({ month: mes, amount: cents(total) }));
    const max = rows.reduce((highest, row) => row.amount > highest ? row.amount : highest, 0n);
    return rows.map(row => ({ ...row, width: max ? Number(row.amount * 1000n / max) / 10 : 0 }));
  });

  readonly variation = computed(() => {
    const paid = this.rows()?.filter(this.hasPayment) ?? [];
    if (paid.length < 2) return null;
    const first = paid[0];
    const last = paid[paid.length - 1];
    const delta = last.amount - first.amount;
    const magnitude = delta < 0n ? -delta : delta;
    const hundredths = (magnitude * 10000n + first.amount / 2n) / first.amount;
    const sign = hundredths === 0n ? '' : delta < 0n ? '−' : '+';
    return { first: first.month, last: last.month, percent: sign + money(hundredths) };
  });

  constructor() {
    inject(DestroyRef).onDestroy(() => { this.version++; });
  }

  ngOnChanges(): void { void this.load(); }

  async load(): Promise<void> {
    const version = ++this.version;
    this.data.set(null);
    this.failed.set(false);
    if (this.hidden) return;
    try {
      const prefix = '/api/spaces/' + encodeURIComponent(this.space);
      const path = prefix + '/commitments/' + encodeURIComponent(this.commitment) + '/payment-trend';
      const report = await this.auth.accountRequest<PaymentTrend>('GET', path);
      if (version === this.version) this.data.set(report);
    } catch {
      if (version === this.version) this.failed.set(true);
    }
  }
}
