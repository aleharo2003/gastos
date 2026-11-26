import { Component, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { installmentLocalDate } from './installment-date';
import { rateUnits } from './money-reference';
import { AuthSession } from './auth-session';
import { UsdReference } from './usd-reference';

@Component({
  selector: 'app-usd-reference-editor',
  imports: [FormsModule],
  template: `
    <details>
      <summary>Cargar cotización manual</summary>
      <form (ngSubmit)="save()">
        <label [for]="id() + '-rate'">Pesos por 1 USD</label>
        <input [id]="id() + '-rate'" name="rate" [(ngModel)]="rate" [disabled]="saving()"
          inputmode="decimal" required maxlength="13" placeholder="Por ejemplo, 1700">
        <label [for]="id() + '-date'">Fecha de la cotización</label>
        <input [id]="id() + '-date'" type="date" name="date" [(ngModel)]="date" [disabled]="saving()" required>
        <button type="submit" [disabled]="saving()">{{ saving() ? 'Guardando…' : 'Guardar cotización' }}</button>
      </form>
      @if (error()) { <p role="alert">{{ error() }}</p> }
      @if (notice()) { <p role="status">{{ notice() }}</p> }
    </details>
    <details #market (toggle)="market.open && loadMarket()">
      <summary>Tipo de dólar de referencia</summary>
      <form (ngSubmit)="saveMarket()">
        <label [for]="id() + '-market'">Cotización automática</label>
        <select [id]="id() + '-market'" name="market" [(ngModel)]="marketType" [disabled]="marketBusy()">
          @for (choice of markets; track choice[0]) { <option [value]="choice[0]">{{ choice[1] }}</option> }
        </select>
        <button type="submit" [disabled]="marketBusy()">Guardar preferencia</button>
      </form>
      <small>Se usa el precio vendedor de DolarApi. Para la misma fecha, tiene prioridad tu cotización manual.</small>
      @if (marketStatus()) { <p role="status">{{ marketStatus() }}</p> }
    </details>
  `,
  styles: [`form { display: grid; gap: .5rem; max-width: 18rem; margin-block: .75rem; }
    button { justify-self: start; }`],
})
export class UsdReferenceEditor {
  readonly space = input.required<string>();
  readonly id = input.required<string>();
  readonly saving = signal(false);
  readonly error = signal('');
  readonly notice = signal('');
  rate = '';
  date = installmentLocalDate();
  private readonly reference = inject(UsdReference);
  private readonly auth = inject(AuthSession);
  readonly markets = [
    ['oficial', 'Oficial'], ['blue', 'Blue'], ['bolsa', 'MEP'], ['contadoconliqui', 'CCL'],
    ['mayorista', 'Mayorista'], ['cripto', 'Cripto'], ['tarjeta', 'Tarjeta'],
  ];
  marketType = 'oficial';
  readonly marketBusy = signal(false);
  readonly marketStatus = signal('');

  private settingsPath(space: string) { return `/api/spaces/${encodeURIComponent(space)}/usd-reference/settings`; }

  async loadMarket(): Promise<void> {
    if (this.marketBusy()) return;
    this.marketBusy.set(true);
    this.marketStatus.set('');
    try {
      const result = await this.auth.accountRequest<{ tipo: string }>('GET', this.settingsPath(this.space()));
      this.marketType = result.tipo;
    } catch {
      this.marketStatus.set('No pudimos consultar la preferencia.');
    } finally { this.marketBusy.set(false); }
  }

  async saveMarket(): Promise<void> {
    if (this.marketBusy()) return;
    const space = this.space();
    this.marketBusy.set(true);
    this.marketStatus.set('');
    try {
      await this.auth.accountRequest('POST', this.settingsPath(space), { tipo: this.marketType });
      await this.reference.refresh(space);
      this.marketStatus.set('Preferencia guardada.');
    } catch {
      this.marketStatus.set('No pudimos confirmar la preferencia. Volvé a intentar.');
    } finally { this.marketBusy.set(false); }
  }

  async save(): Promise<void> {
    if (this.saving()) return;
    this.error.set('');
    this.notice.set('');
    if (!rateUnits(this.rate) || !this.date) {
      this.error.set('Ingresá una fecha y un valor mayor que cero, con hasta cuatro decimales.');
      return;
    }
    this.saving.set(true);
    try {
      await this.reference.save(this.space(), this.date, this.rate.trim().replace(',', '.'));
      this.notice.set('Cotización guardada para la fecha elegida.');
    } catch {
      this.error.set('No pudimos confirmar el guardado. Revisá la fecha y tus permisos e intentá nuevamente.');
    } finally {
      this.saving.set(false);
    }
  }
}
