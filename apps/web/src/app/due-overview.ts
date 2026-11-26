import { Component, computed, DestroyRef, EventEmitter, Input, OnChanges, Output, SimpleChanges, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { installmentLocalDate, prepareInstallmentPayment, submitInstallmentPayment, type InstallmentPayment } from './installment-payment';
import { watchInstallmentDay } from './installment-date';
import { AuthSession } from './auth-session';
import { showAmount } from './expenses';
import { money, rateUnits, reference, type CurrencyTotal } from './money-reference';
import { limitUsage, type LimitPeriod, type PlanLimits } from './planning-math';

type DueTotal = { moneda: string; pendiente: string };
type DueItem = DueTotal & { id: string; nombre: string; numero: number | null; vencimiento: string; estimado: boolean;
  pendiente_ajuste?: boolean; cuenta_id?: string };
type Group = { cantidad: number; totales: DueTotal[]; items: DueItem[] };

type Overview = {
  fecha: string;
  fin_semana: string;
  grupos: Record<'hoy' | 'semana' | 'vencidas', Group> & { proximos?: Group };
  resumen_mes: (DueTotal & { pagado: string })[];
  saldos: { moneda: string; saldo: string }[];
  deudas?: DueTotal[];
  presupuesto: { limites: PlanLimits; gastos: CurrencyTotal[] };
};

@Component({
  selector: 'app-due-overview',
  imports: [FormsModule],
  templateUrl: './due-overview.html',
  styleUrl: './due-overview.css',
})
export class DueOverview implements OnChanges {
  @Input({ required: true }) space = '';
  @Input() active = true;
  @Input() accounts: readonly { id: string; nombre: string }[] = [];
  @Input() moreAccounts = false;
  @Input() accountsLoading = false;
  @Output() loadAccounts = new EventEmitter<void>();
  @Output() paymentSaved = new EventEmitter<void>();
  @Output() openDebts = new EventEmitter<void>();
  @Output() refreshRequested = new EventEmitter<void>();
  readonly overview = signal<Overview | null>(null);
  readonly loading = signal(false);
  readonly error = signal(false);
  readonly hidden = signal(false);
  readonly rate = signal('');
  readonly netCurrency = signal<'ARS' | 'USD'>('ARS');
  readonly netWorth = computed(() => {
    const overview = this.overview();
    if (!overview?.deudas) return null;

    const currency = this.netCurrency();
    const rate = rateUnits(this.rate());
    const assets = overview.saldos.filter(row => !row.saldo.startsWith('-'))
      .map(row => ({ moneda: row.moneda, mes: row.saldo }));
    const liabilities = overview.saldos.filter(row => row.saldo.startsWith('-'))
      .map(row => ({ moneda: row.moneda, mes: row.saldo.slice(1) }))
      .concat(overview.deudas.map(row => ({ moneda: row.moneda, mes: row.pendiente })));
    const assetTotal = reference(assets, 'mes', currency, rate);
    const liabilityTotal = reference(liabilities, 'mes', currency, rate);
    if (assetTotal === null || liabilityTotal === null) return { currency, pending: true } as const;

    const net = assetTotal - liabilityTotal;
    return {
      currency, pending: false, assets: assetTotal, liabilities: liabilityTotal, net,
      estimated: [...assets, ...liabilities].some(row => row.moneda !== currency && row.mes !== '0.00'),
    } as const;
  });
  readonly periods = [{ key: 'diario', label: 'Diario' }, { key: 'semanal', label: 'Semanal' }, { key: 'mensual', label: 'Mensual' }] as const;
  readonly spendingPeriods = [
    { key: 'dia', label: 'Hoy' },
    { key: 'semana', label: 'Esta semana' },
    { key: 'mes', label: 'Este mes' },
  ] as const;
  readonly sections = [
    { key: 'hoy', title: 'Vencen hoy' },
    { key: 'semana', title: 'Resto de la semana' },
    { key: 'vencidas', title: 'Vencidas' },
    { key: 'proximos', title: 'Próximos gastos' },
  ] as const;

  private readonly auth = inject(AuthSession);
  private requestVersion = 0;
  private paymentVersion = 0;
  private pendingPayment?: InstallmentPayment;
  readonly selected = signal<DueItem | null>(null);
  readonly saving = signal(false);
  readonly uncertain = signal(false);
  readonly paymentError = signal('');
  readonly notice = signal('');
  account = '';
  paymentDate = '';
  paymentAmount = '';
  private readonly privacyListener = (event: Event) => {
    this.hidden.set((event as CustomEvent).detail === true);
  };

  private readonly rateListener = (event: Event) => {
    const detail = (event as CustomEvent).detail;
    if (detail?.space === this.space && typeof detail.rate === 'string') this.rate.set(detail.rate);
  };

  constructor() {
    try { this.hidden.set(localStorage.getItem('gastos.totals.hidden') === 'true'); } catch {}
    window.addEventListener('gastos-privacy', this.privacyListener);
    window.addEventListener('gastos-reference', this.rateListener);
    const dayWatch = watchInstallmentDay(day => {
      if (!this.space || !this.active || this.loading() || this.saving()) return false;
      if (this.overview()?.fecha !== day) void this.load();
      return true;
    });
    inject(DestroyRef).onDestroy(() => {
      dayWatch.stop();
      this.requestVersion++;
      this.paymentVersion++;
      window.removeEventListener('gastos-privacy', this.privacyListener);
      window.removeEventListener('gastos-reference', this.rateListener);
    });
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['space']) {
      this.requestVersion++;
      this.paymentVersion++;
      this.overview.set(null);
      this.paymentError.set('');
      this.notice.set('');
      this.saving.set(false);
      this.clearPayment();
    }
    if (this.active && (changes['space'] || changes['active'])) {
      this.rate.set('');
      try {
        const saved = JSON.parse(localStorage.getItem('gastos.reference.' + this.space) ?? 'null');
        if (typeof saved?.rate === 'string' && rateUnits(saved.rate)) this.rate.set(saved.rate);
      } catch {}
      void this.load();
    }
  }

  startPayment(item: DueItem): void {
    if (item.estimado || item.pendiente_ajuste || this.hidden() || this.selected() || this.saving() || this.loading() || this.error()) return;
    this.paymentError.set('');
    this.notice.set('');
    this.account = item.cuenta_id ?? (this.accounts.length === 1 ? this.accounts[0].id : '');
    this.paymentDate = installmentLocalDate();
    this.paymentAmount = item.pendiente;
    this.selected.set(item);
  }

  cancelPayment(): void {
    if (this.saving() || this.uncertain()) return;
    this.clearPayment();
    this.paymentError.set('');
  }

  private clearPayment(): void {
    this.selected.set(null);
    this.pendingPayment = undefined;
    this.uncertain.set(false);
  }

  async pay(): Promise<void> {
    const item = this.selected();
    if (!item || item.estimado || item.pendiente_ajuste || this.saving() || this.hidden()) return;

    const payment = item.cuenta_id ? undefined : this.pendingPayment ?? prepareInstallmentPayment(item.id, {
      cuenta_id: this.account, fecha: this.paymentDate, importe: this.paymentAmount,
    }, item.pendiente, this.accounts);
    if (item.cuenta_id ? !this.paymentDate : !payment) {
      this.paymentError.set(item.cuenta_id ? 'Ingresá la fecha de pago.'
        : 'Elegí una cuenta, una fecha y un importe positivo que no supere el saldo de la cuota.');
      return;
    }

    const version = ++this.paymentVersion;
    this.pendingPayment = payment;
    this.saving.set(true);
    this.paymentError.set('');
    let refresh = false;
    try {
      if (item.cuenta_id) {
        const root = '/api/spaces/' + encodeURIComponent(this.space);
        const path = root + '/accounts/' + encodeURIComponent(item.cuenta_id) +
          '/expenses/' + encodeURIComponent(item.id) + '/pay-pending';
        await this.auth.accountRequest('POST', path, { fecha: this.paymentDate });
      } else {
        await submitInstallmentPayment(this.auth, this.space, payment!);
      }
      if (version !== this.paymentVersion) return;
      this.clearPayment();
      this.notice.set(item.cuenta_id ? 'Pago registrado en Gastos. El saldo se actualizó.'
        : 'Pago registrado. El saldo se actualizó en Deudas y Gastos.');
      this.paymentSaved.emit();
      refresh = true;
    } catch (error) {
      if (version !== this.paymentVersion) return;
      const status = error instanceof HttpErrorResponse ? error.status : 0;
      if (status === 409 || status === 404) {
        this.clearPayment();
        this.paymentError.set(item.cuenta_id ? 'El gasto cambió o la cuenta está archivada. Revisá el estado antes de pagar.'
          : 'La cuota cambió. Revisá el saldo actualizado antes de pagar.');
        refresh = true;
      } else if (status === 400 || status === 403 || status === 422) {
        this.pendingPayment = undefined;
        this.uncertain.set(false);
        this.paymentError.set(status === 403
          ? 'No tenés permiso para registrar pagos.'
          : 'Revisá los datos del pago y volvé a intentar.');
      } else {
        this.uncertain.set(true);
        this.paymentError.set('No pudimos confirmar el pago. Reintentá la misma solicitud para evitar duplicados.');
      }
    } finally {
      if (version === this.paymentVersion) this.saving.set(false);
    }
    if (refresh && version === this.paymentVersion) await this.load();
  }

  refreshOverview(): void {
    this.refreshRequested.emit();
    void this.load();
  }

  async load(): Promise<void> {
    const version = ++this.requestVersion;
    this.loading.set(true);
    this.error.set(false);
    try {
      const result = await this.auth.accountRequest<Overview>(
        'GET', `/api/spaces/${encodeURIComponent(this.space)}/due-overview`,
      );
      if (!result?.grupos || !Array.isArray(result.resumen_mes) || !Array.isArray(result.saldos) || !result.presupuesto?.limites) throw new Error('Resumen inválido');
      if (version === this.requestVersion) this.overview.set(result);
    } catch {
      if (version === this.requestVersion) this.error.set(true);
    } finally {
      if (version === this.requestVersion) this.loading.set(false);
    }
  }

  budgetUsage(period: LimitPeriod) {
    const budget = this.overview()?.presupuesto;
    const limit = budget?.limites[period];
    return limit ? limitUsage(limit, budget?.gastos, period, this.rate()) : null;
  }

  formatBudget(value: bigint): string {
    return this.hidden() ? '••••' : value < 0n ? '−' + money(-value) : money(value);
  }

  hasPending(overview: Overview): boolean {
    return this.sections.some(({ key }) => (overview.grupos[key]?.cantidad ?? 0) > 0);
  }

  accountName(id: string): string {
    return this.accounts.find(account => account.id === id)?.nombre ?? '';
  }

  shortDate(date: string): string {
    const [year, month, day] = date.split('-');
    return `${day}/${month}/${year}`;
  }

  amount(value: string): string {
    return this.hidden() ? '••••' : showAmount(value);
  }
}
