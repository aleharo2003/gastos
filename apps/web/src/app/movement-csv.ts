import { EXPENSE_CATEGORIES } from './expense-categories';
import type { CategoryKind } from './category-catalog';

type MovementRow = {
  fecha: string; tipo: string; descripcion: string; moneda: string; importe: string;
  origen: string | null; destino: string | null; categoria?: string | null; anulado?: boolean;
  moneda_destino?: string; importe_destino?: string;
};

function cell(value: string | null): string {
  const text = value ?? '';
  const safe = /^[\s]*[=+@-]|^[\t\r\n]/u.test(text) ? "'" + text : text;
  return '"' + safe.replaceAll('"', '""') + '"';
}

export function movementCsv(rows: readonly MovementRow[], categoryLabel: (id: string | null, kind: CategoryKind) => string =
  (id, kind) => (kind === 'gasto' ? EXPENSE_CATEGORIES.find(item => item.id === id)?.label : id) ?? 'Sin categoría'): string {
  return '\ufeff' + ['Fecha,Tipo,Descripción,Moneda,Importe,Origen,Destino,Categoría,Moneda recibida,Importe recibido',
    ...rows.map(row => {
      const category = row.tipo === 'gasto' && row.categoria !== undefined
        ? categoryLabel(row.categoria, 'gasto')
        : row.tipo === 'ingreso' && row.categoria ? categoryLabel(row.categoria, 'ingreso') : '';
      const type = row.anulado ? `${row.tipo} anulado` : row.tipo;
      return [row.fecha, type, row.descripcion, row.moneda, row.importe, row.origen, row.destino, category, row.moneda_destino ?? null, row.importe_destino ?? null].map(cell).join(',');
    }),
  ].join('\r\n') + '\r\n';
}
