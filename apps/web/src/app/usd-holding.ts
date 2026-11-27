import { Component, DestroyRef, inject, input, signal } from '@angular/core';
import { AuthSession } from './auth-session';
import { showAmount } from './expenses';

type Holding = {
  usd: string;
  costo_promedio: string | null;
  valor_ars: string | null;
  resultado_ars: string | null;
  resultado_pct: string | null;
  fecha_referencia: string | null;
};

@Component({
  selector: 'app-usd-holding',
  templateUrl: './usd-holding.html',
})
export class UsdHolding {
  readonly space = input.required<string>();
  readonly account = input.required<string>();
  readonly hiddenAmounts = input(false);
  readonly holding = signal<Holding | null>(null);
  readonly busy = signal(false);
  readonly error = signal(false);
  private readonly auth = inject(AuthSession);
  private readonly destroy = inject(DestroyRef);

  async load(): Promise<void> {
    if (this.busy()) return;
    const [space, account] = [this.space(), this.account()];
    const path = `/api/spaces/${encodeURIComponent(space)}/usd-sales/holding?account=${encodeURIComponent(account)}`;
    this.busy.set(true);
    this.error.set(false);
    try {
      const result = await this.auth.accountRequest<Holding>('GET', path);
      if (!this.destroy.destroyed && space === this.space() && account === this.account()) {
        this.holding.set(result);
      }
    } catch {
      if (!this.destroy.destroyed) this.error.set(true);
    } finally {
      if (!this.destroy.destroyed) this.busy.set(false);
    }
  }

  amount(value: string): string {
    return this.hiddenAmounts() ? '••••' : showAmount(value);
  }

  rate(value: string): string {
    return this.hiddenAmounts() ? '••••' : value.replace('.', ',');
  }
}
