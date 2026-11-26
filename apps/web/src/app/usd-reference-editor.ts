import { Component, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { installmentLocalDate } from './installment-date';
import { rateUnits } from './money-reference';
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
