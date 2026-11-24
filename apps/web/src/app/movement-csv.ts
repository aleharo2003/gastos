type MovementRow = {
  fecha: string; tipo: string; descripcion: string; moneda: string; importe: string;
  origen: string | null; destino: string | null;
};

function cell(value: string | null): string {
  const text = value ?? '';
  const safe = /^[\s]*[=+@-]|^[\t\r\n]/u.test(text) ? "'" + text : text;
  return '"' + safe.replaceAll('"', '""') + '"';
}

export function movementCsv(rows: readonly MovementRow[]): string {
  return '\ufeff' + ['Fecha,Tipo,Descripción,Moneda,Importe,Origen,Destino',
    ...rows.map(row => [row.fecha, row.tipo, row.descripcion, row.moneda, row.importe, row.origen, row.destino]
      .map(cell).join(',')),
  ].join('\r\n') + '\r\n';
}
