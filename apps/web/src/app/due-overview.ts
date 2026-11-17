import { Component, DestroyRef, EventEmitter, Input, OnChanges, Output, inject, signal } from '@angular/core';
import { AuthSession } from './auth-session';
import { showAmount } from './expenses';

type DueTotal = { moneda: string; pendiente: string };
type DueItem = DueTotal & { id: string; nombre: string; numero: number; vencimiento: string; estimado: boolean };
type Group = { cantidad: number; totales: DueTotal[]; items: DueItem[] };

type Overview = {
  fecha: string;
  fin_semana: string;
  grupos: Record<'hoy' | 'semana' | 'vencidas', Group>;
  resumen_mes: (DueTotal & { pagado: string })[];
};

@Component({
  selector: 'app-due-overview',
  templateUrl: './due-overview.html',
  styleUrl: './due-overview.css',
})
export class DueOverview implements OnChanges {
  @Input({ required: true }) space = '';
  @Output() openDebts = new EventEmitter<void>();
  readonly overview = signal<Overview | null>(null);
  readonly loading = signal(false);
  readonly error = signal(false);
  readonly hidden = signal(false);
  readonly sections = [
    { key: 'hoy', title: 'Vencen hoy' },
    { key: 'semana', title: 'Resto de la semana' },
    { key: 'vencidas', title: 'Vencidas' },
  ] as const;

  private readonly auth = inject(AuthSession);
  private requestVersion = 0;
  private readonly privacyListener = (event: Event) => {
    this.hidden.set((event as CustomEvent).detail === true);
  };

  constructor() {
    try { this.hidden.set(localStorage.getItem('gastos.totals.hidden') === 'true'); } catch {}
    window.addEventListener('gastos-privacy', this.privacyListener);
    inject(DestroyRef).onDestroy(() => {
      this.requestVersion++;
      window.removeEventListener('gastos-privacy', this.privacyListener);
    });
  }

  ngOnChanges(): void {
    this.overview.set(null);
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
      if (!result?.grupos || !Array.isArray(result.resumen_mes)) throw new Error('Resumen inválido');
      if (version === this.requestVersion) this.overview.set(result);
    } catch {
      if (version === this.requestVersion) this.error.set(true);
    } finally {
      if (version === this.requestVersion) this.loading.set(false);
    }
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
