import { HttpErrorResponse } from '@angular/common/http';
import { Component, EventEmitter, Input, Output, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AuthSession } from './auth-session';
import { type AccountOption, compatibleAccounts } from './account-currency';
import { normalizeAmount } from './expenses';
import { installmentLocalDate } from './installment-date';
import { rateUnits } from './money-reference';

type Offer = { id: string; ronda: string; contraparte: string; fecha: string; tasa: string;
  referencia: string | null; fecha_referencia: string | null; estado: 'vigente' | 'aceptada' | 'rechazada' };

@Component({
  selector: 'app-usd-offers', imports: [FormsModule], templateUrl: './usd-offers.html',
  styles: [`details { margin-block:1rem; } form { display:grid; gap:.625rem; max-width:28rem; }
    button { justify-self:start; } li { margin-block:.75rem; }`],
})
export class UsdOffers {
  @Input({ required: true }) space = '';
  @Input() accounts: AccountOption[] = [];
  @Output() sold = new EventEmitter<void>();
  readonly items = signal<Offer[]>([]);
  readonly offset = signal<number | null>(0);
  readonly busy = signal(false);
  readonly error = signal('');
  readonly notice = signal('');
  readonly selected = signal<Offer | null>(null);
  readonly rounds = computed(() => [...new Map(this.items().filter(o => o.estado === 'vigente')
    .map(o => [o.ronda,o])).values()]);
  readonly warning = computed(() => {
    const selected = this.selected();
    return selected && this.items().some(o => o.ronda === selected.ronda && o.estado === 'vigente'
      && (rateUnits(o.tasa) ?? 0n) > (rateUnits(selected.tasa) ?? 0n));
  });
  round = '';
  counterparty = '';
  rate = '';
  source = '';
  destination = '';
  date = installmentLocalDate();
  usd = '';
  confirmBetter = false;
  conflict = false;
  private pending?: { id: string; ronda: string; contraparte: string; tasa: string };
  private readonly auth = inject(AuthSession);

  private get path() { return `/api/spaces/${encodeURIComponent(this.space)}/usd-offers`; }
  get sources() { return compatibleAccounts(this.accounts, 'USD'); }
  get destinations() { return compatibleAccounts(this.accounts, 'ARS').filter(c => c.id !== this.source); }

  private async list(more: boolean): Promise<void> {
    const offset = more ? this.offset() : 0;
    if (offset === null) return;
    const page = await this.auth.accountRequest<{ items: Offer[]; next_offset: number | null }>(
      'GET', this.path + '?offset=' + offset);
    this.items.set(more ? [...this.items(), ...page.items] : page.items);
    this.offset.set(page.next_offset);
  }

  async load(more = false): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    this.error.set('');
    try { await this.list(more); }
    catch { this.error.set('No pudimos cargar las ofertas.'); }
    finally { this.busy.set(false); }
  }

  changeRound(value: string): void {
    this.round = value;
    this.pending = undefined;
  }

  async add(): Promise<void> {
    if (this.busy()) return;
    const tasa = this.rate.trim().replace(',', '.');
    const contraparte = this.counterparty.trim();
    if (!rateUnits(tasa) || !contraparte) {
      this.error.set('Ingresá la contraparte y un precio positivo con hasta cuatro decimales.');
      return;
    }
    if (!this.pending || (this.round && this.pending.ronda !== this.round) ||
      this.pending.tasa !== tasa || this.pending.contraparte !== contraparte) {
      this.pending = { id: crypto.randomUUID(), ronda: this.round || crypto.randomUUID(), contraparte, tasa };
    }
    this.busy.set(true);
    this.error.set('');
    this.notice.set('');
    try {
      await this.auth.accountRequest('POST', this.path, this.pending);
      this.round = this.pending.ronda;
      this.pending = undefined;
      this.counterparty = ''; this.rate = '';
      this.notice.set('Oferta registrada.');
      await this.list(false);
    } catch { this.error.set('No pudimos confirmar la oferta. Revisá la ronda y reintentá.'); }
    finally { this.busy.set(false); }
  }

  select(offer: Offer | null): void {
    this.selected.set(offer);
    this.confirmBetter = false;
    this.conflict = false;
    this.error.set('');
  }

  async accept(): Promise<void> {
    const offer = this.selected(), usd = normalizeAmount(this.usd);
    if (!offer || this.busy() || !usd || !this.date || !this.sources.some(a => a.id === this.source)
      || !this.destinations.some(a => a.id === this.destination)) return;
    if ((this.warning() || this.conflict) && !this.confirmBetter) return;
    this.busy.set(true);
    this.error.set('');
    this.notice.set('');
    try {
      await this.auth.accountRequest('POST', this.path, { oferta_id: offer.id, usd, fecha: this.date,
        origen_id: this.source, destino_id: this.destination, confirmar_mejor: this.confirmBetter });
      if (this.round === offer.ronda) this.round = '';
      this.select(null);
      this.sold.emit();
      this.notice.set('Oferta aceptada. La venta y los saldos se actualizaron.');
      await this.list(false);
    } catch (err) {
      this.conflict = err instanceof HttpErrorResponse && err.status === 409;
      this.confirmBetter = false;
      this.error.set(this.conflict
        ? 'La ronda cambió o hay una oferta mejor. Revisá la ronda antes de confirmar.'
        : 'No pudimos confirmar la venta. Revisá los datos y reintentá.');
    } finally { this.busy.set(false); }
  }
}
