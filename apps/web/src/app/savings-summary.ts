import { Component, DestroyRef, EventEmitter, Input, OnChanges, Output, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { UsdReference } from './usd-reference';
import { UsdReferenceEditor } from './usd-reference-editor';
import { AuthSession } from './auth-session';
import { installmentLocalDate } from './installment-date';
import { cents, money, rateUnits } from './money-reference';

type Currency = 'ARS' | 'USD' | 'EUR';
type Amount = { moneda: Currency; total: string };
type Account = { id: string; nombre: string; activa: boolean; saldos: Amount[] };
type Report = {
  mes: string; hasta: string; fecha_saldos: string; next_offset: number | null;
  actividad: (Amount & { fijado?: { usd: string; ars: string }; tipo: 'cuotas' | 'otros_gastos' | 'ingresos_anuales' })[];
  ingresos: (Amount & { concepto: string | null })[];
  cuentas: Account[]; saldo_total: Amount[];
};
type Totals = Record<Currency, bigint>;
const currencies: Currency[] = ['ARS', 'USD', 'EUR'];
const zero = (): Totals => ({ ARS: 0n, USD: 0n, EUR: 0n });

function amounts(rows: Amount[]): Totals {
  const totals = zero();
  for (const row of rows) {
    const negative = row.total.startsWith('-');
    totals[row.moneda] += negative ? -cents(row.total.slice(1)) : cents(row.total);
  }
  return totals;
}

function rounded(numerator: bigint, denominator: bigint): bigint {
  return numerator < 0n ? -rounded(-numerator, denominator) : (numerator + denominator / 2n) / denominator;
}

@Component({
  selector: 'app-savings-summary',
  imports: [FormsModule, UsdReferenceEditor],
  templateUrl: './savings-summary.html',
  styleUrl: './savings-summary.css',
})
export class SavingsSummary implements OnChanges {
  @Input({ required: true }) space = '';
  @Input() revision = 0;
  @Output() registerIncome = new EventEmitter<void>();

  readonly currentMonth = () => installmentLocalDate().slice(0, 7);
  month = this.currentMonth();
  readonly data = signal<Report | null>(null);
  readonly loading = signal(false);
  readonly error = signal('');
  readonly hidden = signal(false);
  readonly rate = signal('');
  readonly rateDate = signal('');
  readonly equivalents = signal(false);
  private readonly usdReference = inject(UsdReference);
  private request = 0;
  private storedSpace = '';
  private readonly auth = inject(AuthSession);
  private readonly privacy = (event: Event) => this.hidden.set((event as CustomEvent).detail === true);
  private readonly referenceChanged = (event: Event) => {
    if ((event as CustomEvent).detail?.space === this.space) this.loadReference();
  };

  readonly monthRows = computed(() => {
    const report = this.data();
    if (!report) return null;
    const sources = new Map<string | null, Amount[]>();
    for (const row of report.ingresos) {
      const group = sources.get(row.concepto) ?? [];
      group.push(row);
      sources.set(row.concepto, group);
    }
    const income = amounts(report.ingresos);
    const installments = amounts(report.actividad.filter(row => row.tipo === 'cuotas'));
    const other = amounts(report.actividad.filter(row => row.tipo === 'otros_gastos'));
    const fixed = (kind: 'cuotas' | 'otros_gastos') => {
      const pair = report.actividad.find(row => row.tipo === kind && row.moneda === 'USD')?.fijado;
      return { usd: cents(pair?.usd ?? '0.00'), ars: cents(pair?.ars ?? '0.00') };
    };
    const installmentsFixed = fixed('cuotas'), otherFixed = fixed('otros_gastos');
    const expensesFixed = { usd: installmentsFixed.usd + otherFixed.usd, ars: installmentsFixed.ars + otherFixed.ars };
    const netFixed = { usd: -expensesFixed.usd, ars: -expensesFixed.ars };
    const annual = amounts(report.actividad.filter(row => row.tipo === 'ingresos_anuales'));
    const expenses = zero();
    const net = zero();
    for (const currency of currencies) {
      expenses[currency] = installments[currency] + other[currency];
      net[currency] = income[currency] - expenses[currency];
    }
    return {
      sources: [...sources].map(([concept, rows]) => ({ concept, totals: amounts(rows) })),
      income, installments, other, annual, expenses, net, installmentsFixed, otherFixed, expensesFixed, netFixed,
    };
  });

  readonly columns = computed(() => {
    const report = this.data();
    const hasEuro = report && [...report.ingresos, ...report.actividad, ...report.saldo_total,
      ...report.cuentas.flatMap(account => account.saldos)].some(row => row.moneda === 'EUR' && row.total !== '0.00');
    return hasEuro ? currencies : currencies.slice(0, 2);
  });

  constructor() {
    try { this.hidden.set(localStorage.getItem('gastos.totals.hidden') === 'true'); } catch {}
    window.addEventListener('gastos-privacy', this.privacy);
    window.addEventListener('gastos-reference', this.referenceChanged);
    inject(DestroyRef).onDestroy(() => {
      this.request++;
      window.removeEventListener('gastos-privacy', this.privacy);
      window.removeEventListener('gastos-reference', this.referenceChanged);
    });
  }

  ngOnChanges(): void {
    if (this.storedSpace !== this.space) {
      this.storedSpace = this.space;
      this.data.set(null);
      this.month = this.currentMonth();
      this.loadReference();
    }
    void this.load();
  }

  private loadReference(): void {
    const reference = this.usdReference.current(this.space);
    this.rate.set(reference?.rate ?? '');
    this.rateDate.set(reference?.date ?? '');
  }

  async load(more = false): Promise<void> {
    const previous = this.data();
    const month = more ? (previous?.mes ?? this.month) : this.month;
    if (!/^(19[0-9]{2}|20[0-9]{2})-(0[1-9]|1[0-2])$/.test(month) || month > this.currentMonth()) {
      this.error.set('Elegí un mes hasta el actual.');
      return;
    }
    const offset = more ? previous?.next_offset : 0;
    if (offset == null || (more && this.loading())) return;
    const request = ++this.request;
    this.loading.set(true);
    this.error.set('');
    try {
      const path = '/api/spaces/' + encodeURIComponent(this.space) + '/savings-summary?month=' + month + '&offset=' + offset;
      const report = await this.auth.accountRequest<Report>('GET', path);
      if (request !== this.request) return;
      if (report?.mes !== month || !Array.isArray(report.cuentas)) throw new Error();
      this.data.set({ ...report, cuentas: [...new Map([
        ...(more ? previous?.cuentas ?? [] : []), ...report.cuentas,
      ].map(account => [account.id, account])).values()] });
    } catch {
      if (request === this.request) this.error.set('No pudimos cargar el resumen. Volvé a intentar.');
    } finally {
      if (request === this.request) this.loading.set(false);
    }
  }

  readonly toTotals = amounts;

  display(totals: Totals, currency: Currency, fixed = { usd: 0n, ars: 0n }): string {
    if (this.hidden()) return '••••';
    const rate = this.equivalents() ? rateUnits(this.rate()) : null;
    let value = totals[currency];
    if (currency === 'ARS' && this.equivalents()) {
      value += fixed.ars;
      if (rate) value += rounded((totals.USD - fixed.usd) * rate, 10000n);
    }
    if (rate && currency === 'USD') value += rounded(totals.ARS * 10000n, rate);
    return value < 0n ? '−' + money(-value) : money(value);
  }
}
