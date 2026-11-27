import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { cents, money, rateUnits } from './money-reference';

export type PaymentQuote = { fuente: 'referencia' | 'ultima_venta' | 'manual'; tasa?: string };
export type SavedQuote = { tasa_pago?: string; fuente_tasa_pago?: string; importe_ars_pago?: string };

export function estimatedArs(amount: string, rate: string): string | null {
  const units = rateUnits(rate);
  return units && /^\d+\.\d{2}$/.test(amount) ? money((cents(amount) * units + 5000n) / 10000n) : null;
}

@Component({
  selector: 'app-payment-quote',
  imports: [FormsModule],
  template: `
    <label [for]="fieldId">Tipo de cambio del pago</label>
    <select [id]="fieldId" [ngModelOptions]="{standalone:true}" [(ngModel)]="source"
      (ngModelChange)="emit()" [disabled]="disabled">
      <option value="">Referencia disponible para la fecha</option>
      <option value="ultima_venta">Última venta de USD</option>
      <option value="manual">Ingresar cotización manual</option>
    </select>
    @if (source === 'manual') {
      <label [for]="fieldId + '-value'">Pesos por USD</label>
      <input [id]="fieldId + '-value'" [ngModelOptions]="{standalone:true}" [(ngModel)]="rate"
        (ngModelChange)="emit()" inputmode="decimal" maxlength="13" [disabled]="disabled">
    }
  `,
})
export class PaymentQuoteEditor {
  @Input({required:true}) fieldId = '';
  @Input() disabled = false;
  @Output() quoteChange = new EventEmitter<PaymentQuote | undefined>();
  source: '' | 'ultima_venta' | 'manual' = '';
  rate = '';

  emit() {
    this.quoteChange.emit(this.source === 'manual' ? { fuente: this.source, tasa: this.rate.trim().replace(',', '.') }
      : this.source ? { fuente: this.source } : undefined);
  }
}
