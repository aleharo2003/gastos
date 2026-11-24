import { EXPENSE_CATEGORIES } from './expense-categories';

type MovementRow = {
  fecha: string; tipo: string; descripcion: string; moneda: string; importe: string;
  origen: string | null; destino: string | null; categoria?: string | null;
};

function cell(value: string | null): string {
  const text = value ?? '';
  const safe = /^[\s]*[=+@-]|^[\t\r\n]/u.test(text) ? "'" + text : text;
  return '"' + safe.replaceAll('"', '""') + '"';
}

export function movementCsv(rows: readonly MovementRow[]): string {
  return '\ufeff' + ['Fecha,Tipo,Descripción,Moneda,Importe,Origen,Destino,Categoría',
    ...rows.map(row => {
      const category = row.tipo === 'gasto' && row.categoria !== undefined
        ? EXPENSE_CATEGORIES.find(item => item.id === row.categoria)?.label ?? 'Sin categoría' : '';
      return [row.fecha, row.tipo, row.descripcion, row.moneda, row.importe, row.origen, row.destino, category].map(cell).join(',');
    }),
  ].join('\r\n') + '\r\n';
}
