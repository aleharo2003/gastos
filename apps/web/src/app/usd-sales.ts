import { Component, DestroyRef, EventEmitter, Input, OnChanges, Output, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { UsdOffers } from './usd-offers';
import { AnomalyCancelled, confirmAnomaly } from './confirm-anomaly';
import { AuthSession } from './auth-session';
import { type AccountOption, compatibleAccounts } from './account-currency';
import { normalizeAmount, showAmount } from './expenses';
import { installmentLocalDate } from './installment-date';

type Sale = {
  id: string; origen_id: string; destino_id: string; fecha: string; contraparte: string;
  usd: string; ars: string; tasa: string; referencia: string | null;
  fecha_referencia: string | null; diferencia_pct: string | null;
};
type Draft = Pick<Sale, 'origen_id' | 'destino_id' | 'fecha' | 'contraparte' | 'usd' | 'ars'>;
type Analysis = {
  contrapartes: { contraparte: string; operaciones: number; comparadas: number; ofertas: number; diferencia: string | null }[];
  rondas: { ronda: string; fecha: string; contraparte: string; mejor_contraparte: string; aceptada: string;
    mejor: string; usd: string; diferencia_ars: string }[];
};
type SalePage = { items: Sale[]; next_offset: number | null };

@Component({
  selector: 'app-usd-sales', imports: [FormsModule, UsdOffers],
  templateUrl: './usd-sales.html',
  styles: [`form { display:grid; gap:.625rem; max-width:28rem; }
    button { justify-self:start; } ul { padding-inline-start:1.25rem; } li { margin-block:.75rem; }`],
})
export class UsdSales implements OnChanges {
  @Input({ required: true }) space = '';
  @Input() accounts: AccountOption[] = [];
  @Input() moreAccounts = false;
  @Input() accountsLoading = false;
  @Output() loadAccounts = new EventEmitter<void>();
  @Output() changed = new EventEmitter<void>();
  readonly analysis = signal<Analysis | null>(null);
  readonly analysisLoading = signal(false);
  readonly analysisError = signal('');
  readonly sales = signal<Sale[]>([]);
  readonly offset = signal<number | null>(0);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly notice = signal('');
  readonly showAmount = showAmount;
  readonly today = installmentLocalDate;
  source = '';
  destination = '';
  date = this.today();
  counterparty = '';
  dollars = '';
  pesos = '';
  protected readonly auth = inject(AuthSession);
  private pending?: Draft & { id: string };
  private alive = true;

  constructor() { inject(DestroyRef).onDestroy(() => { this.alive = false; }); }

  protected get path() { return `/api/spaces/${encodeURIComponent(this.space)}/usd-sales`; }
  get sources() { return compatibleAccounts(this.accounts, 'USD'); }
  get destinations() { return compatibleAccounts(this.accounts, 'ARS').filter(c => c.id !== this.source); }
  accountName(id: string) { return this.accounts.find(account => account.id === id)?.nombre ?? 'Cuenta'; }

  ngOnChanges(changes: Record<string, unknown>): void {
    if (changes['space'] && this.space) void this.load();
  }

  async load(more = false): Promise<void> {
    const offset = more ? this.offset() : 0;
    if (offset === null || this.loading()) return;
    const path = this.path;
    this.loading.set(true);
    this.error.set('');
    try {
      const page = await this.auth.accountRequest<SalePage>('GET', path + '?offset=' + offset);
      if (this.alive && path === this.path) {
        this.sales.set(more ? [...this.sales(), ...page.items] : page.items);
        this.offset.set(page.next_offset);
      }
    } catch {
      if (this.alive) this.error.set('No pudimos cargar las ventas.');
    } finally { if (this.alive) this.loading.set(false); }
  }

  async loadAnalysis(): Promise<void> {
    if (this.analysisLoading()) return;
    this.analysisLoading.set(true);
    this.analysisError.set('');
    try {
      const result = await this.auth.accountRequest<Analysis>('GET', this.path + '/analysis');
      if (this.alive) this.analysis.set(result);
    } catch {
      if (this.alive) this.analysisError.set('No pudimos cargar el análisis de contrapartes.');
    } finally { if (this.alive) this.analysisLoading.set(false); }
  }

  refreshAfterOffer(): void {
    this.changed.emit();
      if (this.analysis()) void this.loadAnalysis();
    void this.load();
  }

  async save(): Promise<void> {
    if (this.saving()) return;
    this.notice.set('');
    const usd = normalizeAmount(this.dollars);
    const ars = normalizeAmount(this.pesos);
    const contraparte = this.counterparty.trim();
    if (!usd || !ars || !contraparte || !this.date ||
      !this.sources.some(a => a.id === this.source) || !this.destinations.some(a => a.id === this.destination)) {
      this.error.set('Completá ambos importes, la fecha, la contraparte y las dos cuentas.');
      return;
    }
    const draft: Draft = { origen_id: this.source, destino_id: this.destination,
      fecha: this.date, contraparte, usd, ars };
    if (!this.pending || Object.entries(draft).some(([key, value]) => this.pending?.[key as keyof Draft] !== value)) {
      this.pending = { ...draft, id: crypto.randomUUID() };
    }
    this.saving.set(true);
    this.error.set('');
    try {
      const payload = this.pending;
      await confirmAnomaly(confirmation => this.auth.accountRequest('POST', this.path, { ...payload, ...confirmation }));
      if (!this.alive) return;
      this.pending = undefined;
      this.dollars = ''; this.pesos = ''; this.counterparty = '';
      this.notice.set('Venta registrada. Se actualizaron ambas cuentas.');
      this.changed.emit();
      if (this.analysis()) void this.loadAnalysis();
      await this.load();
    } catch (error) {
      if (error instanceof AnomalyCancelled) return;
      if (this.alive) this.error.set('No pudimos confirmar la venta. Revisá los datos y reintentá.');
    } finally { if (this.alive) this.saving.set(false); }
  }
}
