import { inject, Injectable } from '@angular/core';
import { AuthSession } from './auth-session';
import { rateUnits } from './money-reference';

type SavedRate = { fecha: string; tasa: string };
type ReferenceResponse = { cotizacion: SavedRate | null };
export type UsdRate = { rate: string; date: string };

@Injectable({ providedIn: 'root' })
export class UsdReference {
  private readonly auth = inject(AuthSession);
  private readonly currentRates = new Map<string, UsdRate | null>();
  private readonly revisions = new Map<string, number>();

  current(space: string): UsdRate | null {
    return this.currentRates.get(space) ?? this.legacy(space);
  }

  async refresh(space: string): Promise<void> {
    await this.request(space, 'GET');
  }

  async save(space: string, date: string, rate: string): Promise<void> {
    await this.request(space, 'POST', { fecha: date, tasa: rate });
  }

  private async request(space: string, method: 'GET' | 'POST', body?: SavedRate): Promise<void> {
    const revision = (this.revisions.get(space) ?? 0) + 1;
    this.revisions.set(space, revision);
    const path = `/api/spaces/${encodeURIComponent(space)}/usd-reference`;
    const response = await this.auth.accountRequest<ReferenceResponse>(method, path, body);
    const saved = response?.cotizacion;
    if (saved !== null && (!saved || typeof saved.tasa !== 'string' || !rateUnits(saved.tasa)
      || typeof saved.fecha !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(saved.fecha))) {
      throw new Error('Cotización inválida');
    }
    if (this.revisions.get(space) !== revision) return;
    this.currentRates.set(space, saved ? { rate: saved.tasa.replace(/(\.\d*?[1-9])0+$|\.0+$/, '$1'), date: saved.fecha } : null);
    const current = this.current(space);
    window.dispatchEvent(new CustomEvent('gastos-reference', {
      detail: { space, rate: current?.rate ?? '', date: current?.date ?? '' },
    }));
  }

  private legacy(space: string): UsdRate | null {
    try {
      const saved = JSON.parse(localStorage.getItem('gastos.reference.' + space) ?? 'null');
      if (typeof saved?.rate === 'string' && rateUnits(saved.rate) && typeof saved.date === 'string'
        && /^\d{4}-\d{2}-\d{2}$/.test(saved.date)) return { rate: saved.rate, date: saved.date };
    } catch {}
    return null;
  }
}
