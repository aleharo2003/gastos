import type { PaymentQuote, SavedQuote } from './payment-quote';
import { AuthSession } from './auth-session';
import { normalizeAmount } from './expenses';
import { cents } from './money-reference';

export type Payment = SavedQuote & {
  id: string;
  espacio_id: string;
  cuota_id: string;
  cuenta_id: string;
  fecha: string;
  moneda: string;
  importe: string;
};

type PaymentDetails = Pick<Payment, 'cuenta_id' | 'fecha' | 'importe'> & { cotizacion_pago?: PaymentQuote };
export type InstallmentPayment = { quota: string; body: PaymentDetails & { id: string } };

export function prepareInstallmentPayment(
  quota: string,
  details: PaymentDetails,
  balance: string,
  accounts: readonly { id: string }[],
  previous?: InstallmentPayment,
): InstallmentPayment | undefined {
  const amount = normalizeAmount(details.importe);
  if (!amount || !details.fecha || !accounts.some(account => account.id === details.cuenta_id) ||
      cents(amount) > cents(balance)) return undefined;

  const body = { ...details, importe: amount };
  if (previous?.quota === quota && previous.body.cuenta_id === body.cuenta_id &&
      previous.body.fecha === body.fecha && previous.body.importe === body.importe &&
      previous.body.cotizacion_pago?.fuente === body.cotizacion_pago?.fuente &&
      previous.body.cotizacion_pago?.tasa === body.cotizacion_pago?.tasa) return previous;
  return { quota, body: { id: crypto.randomUUID(), ...body } };
}

export function submitInstallmentPayment(auth: AuthSession, space: string, payment: InstallmentPayment) {
  const path = `/api/spaces/${encodeURIComponent(space)}/installments/${encodeURIComponent(payment.quota)}/payments`;
  return auth.accountRequest<Payment>('POST', path, payment.body);
}

export { installmentLocalDate } from './installment-date';
