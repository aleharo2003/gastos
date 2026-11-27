export type PaymentQuote = { fuente: 'referencia' | 'ultima_venta' | 'manual'; tasa?: string };
export type SavedQuote = { tasa_pago?: string; fuente_tasa_pago?: string; importe_ars_pago?: string };
const sources = ['referencia', 'ultima_venta', 'manual'];

export function validPaymentQuote(value: unknown): boolean {
  if (value === undefined) return true;
  const quote = value as PaymentQuote;
  if (!quote || typeof quote !== 'object' || !sources.includes(quote.fuente) ||
      Object.keys(quote).some(key => key !== 'fuente' && key !== 'tasa')) return false;
  if (quote.fuente !== 'manual') return quote.tasa === undefined;
  return typeof quote.tasa === 'string' && /^(?:0|[1-9][0-9]{0,7})(?:\.[0-9]{1,4})?$/.test(quote.tasa)
    && /[1-9]/.test(quote.tasa);
}

export function savedQuote(row: SavedQuote): SavedQuote {
  if (row.tasa_pago === undefined && row.fuente_tasa_pago === undefined && row.importe_ars_pago === undefined) return {};
  if (typeof row.tasa_pago !== 'string' || !/^\d{1,16}\.\d{4}$/.test(row.tasa_pago)
    || typeof row.fuente_tasa_pago !== 'string' || !sources.includes(row.fuente_tasa_pago)
    || typeof row.importe_ars_pago !== 'string' || !/^\d{1,28}\.\d{2}$/.test(row.importe_ars_pago)) throw new Error();
  return { tasa_pago: row.tasa_pago, fuente_tasa_pago: row.fuente_tasa_pago, importe_ars_pago: row.importe_ars_pago };
}

export type FrozenPair = { usd: string; ars: string };

export function frozenPair(value: unknown, total: string): FrozenPair {
  const v = value as FrozenPair;
  const amount = (s: unknown): s is string => typeof s === 'string' && /^(?:0|[1-9]\d{0,30})\.\d{2}$/.test(s);
  if (!v || !amount(v.usd) || !amount(v.ars) || BigInt(v.usd.replace('.', '')) > BigInt(total.replace('.', ''))) throw new Error();
  return { usd: v.usd, ars: v.ars };
}

export function frozenPeriods(row: { moneda: string; dia: string; mes: string; semana?: string; fijados?: unknown }) {
  if (row.fijados === undefined) return {};
  const periods = row.fijados as { dia?: unknown; mes?: unknown; semana?: unknown };
  if (!periods || row.moneda !== 'USD' || row.semana === undefined) throw new Error();
  return { fijados: { dia: frozenPair(periods.dia,row.dia), mes: frozenPair(periods.mes,row.mes),
    semana: frozenPair(periods.semana,row.semana) } };
}
