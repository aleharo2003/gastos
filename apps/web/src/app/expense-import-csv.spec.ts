import { parseImportCsv, previewImport } from './expense-import-csv';

it('lee CSV de Excel, conserva comillas y permite cambiar el orden de columnas', () => {
  const { headers, records } = parseImportCsv('\ufeffMonto;Fecha;Descripción\r\n0010,5;2/1/2026;"Papel; ""A4"""\r\n', ';');
  expect(previewImport(records, headers.length, { fecha: 1, descripcion: 2, importe: 0 }, 'USD')).toEqual([
    { line: 2, expense: { fecha: '2026-01-02', descripcion: 'Papel; "A4"', importe: '10.50', moneda: 'USD' } },
  ]);
});

it('marca cada fila inválida y conserva las demás', () => {
  const { headers, records } = parseImportCsv('Fecha,Descripción,Importe\n2026-02-30,Café,2.00\n2026-03-01,Pan,n/a\n2026-03-01,Pan,3\n', ',');
  const rows = previewImport(records, headers.length, { fecha: 0, descripcion: 1, importe: 2 }, 'ARS');
  expect(rows.map(row => row.line)).toEqual([2, 3, 4]);
  expect(rows[0].error).toContain('Fecha');
  expect(rows[1].error).toContain('Importe');
  expect(rows[2].expense?.importe).toBe('3.00');
});
