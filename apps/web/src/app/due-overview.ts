import { Component, DestroyRef, EventEmitter, Input, OnChanges, Output, SimpleChanges, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { installmentLocalDate, prepareInstallmentPayment, submitInstallmentPayment, type InstallmentPayment } from './installment-payment';
import { AuthSession } from './auth-session';
import { showAmount } from './expenses';
import { money, rateUnits, type CurrencyTotal } from './money-reference';
import { limitUsage, type PlanMoney } from './planning-math';

type DueTotal = { moneda: string; pendiente: string };
type DueItem = DueTotal & { id: string; nombre: string; numero: number; vencimiento: string; estimado: boolean };
type Group = { cantidad: number; totales: DueTotal[]; items: DueItem[] };

type Overview = {
  fecha: string;
  fin_semana: string;
  grupos: Record<'hoy' | 'semana' | 'vencidas', Group>;
  resumen_mes: (DueTotal & { pagado: string })[];
  saldos: { moneda: string; saldo: string }[];
  presupuesto: { limites: Record<'diario' | 'semanal', PlanMoney | null>; gastos: CurrencyTotal[] };
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
  readonly overview = signal<Overview | null>(null);
  readonly loading = signal(false);
  readonly error = signal(false);
  readonly hidden = signal(false);
  readonly rate = signal('');
  readonly periods = [{ key: 'diario', label: 'Diario' }, { key: 'semanal', label: 'Semanal' }] as const;
  readonly sections = [
    { key: 'hoy', title: 'Vencen hoy' },
    { key: 'semana', title: 'Resto de la semana' },
    { key: 'vencidas', title: 'Vencidas' },
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
    inject(DestroyRef).onDestroy(() => {
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
    if (item.estimado || this.hidden() || this.selected() || this.saving() || this.loading() || this.error()) return;
    this.paymentError.set('');
    this.notice.set('');
    this.account = this.accounts.length === 1 ? this.accounts[0].id : '';
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
    if (!item || item.estimado || this.saving() || this.hidden()) return;

    const payment = this.pendingPayment ?? prepareInstallmentPayment(item.id, {
      cuenta_id: this.account, fecha: this.paymentDate, importe: this.paymentAmount,
    }, item.pendiente, this.accounts);
    if (!payment) {
      this.paymentError.set('Elegí una cuenta, una fecha y un importe positivo que no supere el saldo de la cuota.');
      return;
    }

    const version = ++this.paymentVersion;
    this.pendingPayment = payment;
    this.saving.set(true);
    this.paymentError.set('');
    let refresh = false;
    try {
      await submitInstallmentPayment(this.auth, this.space, payment);
      if (version !== this.paymentVersion) return;
      this.clearPayment();
      this.notice.set('Pago registrado. El saldo se actualizó en Deudas y Gastos.');
      this.paymentSaved.emit();
      refresh = true;
    } catch (error) {
      if (version !== this.paymentVersion) return;
      const status = error instanceof HttpErrorResponse ? error.status : 0;
      if (status === 409 || status === 404) {
        this.clearPayment();
        this.paymentError.set('La cuota cambió. Revisá el saldo actualizado antes de pagar.');
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

  budgetUsage(period: 'diario' | 'semanal') {
    const budget = this.overview()?.presupuesto;
    const limit = budget?.limites[period];
    return limit ? limitUsage(limit, budget?.gastos, period, this.rate()) : null;
  }

  formatBudget(value: bigint): string {
    return this.hidden() ? '••••' : money(value);
  }

  hasPending(overview: Overview): boolean {
    return this.sections.some(({ key }) => overview.grupos[key].cantidad > 0);
  }

  shortDate(date: string): string {
    const [year, month, day] = date.split('-');
    return `${day}/${month}/${year}`;
  }

  amount(value: string): string {
    return this.hidden() ? '••••' : showAmount(value);
  }
}
