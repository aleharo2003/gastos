export const MAX_CSV_ROWS = 1000;
export const MAX_CSV_BYTES = 256 * 1024;

export type ImportExpense = { fecha: string; descripcion: string; importe: string; moneda: string };
export type ImportRow = { line: number; expense?: ImportExpense; error?: string };
export type ImportMapping = Record<'fecha' | 'descripcion' | 'importe', number>;

function parseRecords(text: string, separator: string): string[][] {
  const records: string[][] = [];
  let record: string[] = [];
  let cell = '';
  let quoted = false;
  let closedQuote = false;
  const finishCell = () => {
    record.push(cell);
    if (record.length > 80) throw new Error('El CSV admite hasta 80 columnas.');
    cell = '';
    closedQuote = false;
  };
  const finishRecord = () => {
    finishCell();
    records.push(record);
    if (records.length > MAX_CSV_ROWS + 1) throw new Error('El CSV admite hasta 1.000 filas de datos.');
    record = [];
  };
  for (let index = 0; index < text.length; index++) {
    const char = text[index];
    if (quoted) {
      if (char !== '"') cell += char;
      else if (text[index + 1] === '"') { cell += '"'; index++; }
      else { quoted = false; closedQuote = true; }
    } else if (char === separator) finishCell();
    else if (char === '\n' || char === '\r') {
      if (char === '\r' && text[index + 1] === '\n') index++;
      finishRecord();
    } else if (char === '"' && !cell && !closedQuote) quoted = true;
    else if (char === '"' || closedQuote) throw new Error('Hay una columna con comillas inválidas.');
    else cell += char;
  }
  if (quoted) throw new Error('Hay una columna sin comilla de cierre.');
  if (cell || record.length || closedQuote) finishRecord();
  return records;
}

export function parseImportCsv(text: string, separator: ',' | ';'): { headers: string[]; records: string[][] } {
  const [headers, ...records] = parseRecords(text.replace(/^\uFEFF/, ''), separator);
  if (!headers || headers.length < 3 || !records.length) {
    throw new Error('El CSV necesita encabezados, tres columnas y al menos una fila. Revisá el separador.');
  }
  return { headers, records };
}

function parseDate(input: string): string | null {
  const local = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(input);
  const value = local ? local[3] + '-' + local[2].padStart(2, '0') + '-' + local[1].padStart(2, '0') : input;
  if (!/^[1-9]\d{3}-\d{2}-\d{2}$/.test(value)) return null;
  const date = new Date(value + 'T00:00:00Z');
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value ? value : null;
}

export function previewImport(
  records: string[][], width: number, mapping: ImportMapping, currency: string,
): ImportRow[] {
  if (new Set(Object.values(mapping)).size !== 3 ||
      Object.values(mapping).some(index => index < 0 || index >= width)) return [];
  return records.flatMap<ImportRow>((record, index) => {
    if (record.every(value => !value.trim())) return [];
    const line = index + 2;
    if (record.length !== width) return [{ line, error: 'La cantidad de columnas difiere del encabezado.' }];
    const fecha = parseDate(record[mapping.fecha].trim());
    const descripcion = record[mapping.descripcion].trim();
    const amount = record[mapping.importe].trim().replace(',', '.');
    if (!fecha) return [{ line, error: 'Fecha inválida. Usá AAAA-MM-DD o DD/MM/AAAA.' }];
    if (!descripcion || [...descripcion].length > 160 || /[\x00-\x1f\x7f]/.test(descripcion)) {
      return [{ line, error: 'La descripción debe tener entre 1 y 160 caracteres en una sola línea.' }];
    }
    if (!/^\d{1,12}(?:\.\d{1,2})?$/.test(amount) || !/[1-9]/.test(amount)) {
      return [{ line, error: 'Importe inválido. Usá un importe positivo sin separador de miles.' }];
    }
    const [integer, fraction = ''] = amount.split('.');
    const importe = integer.replace(/^0+(?=\d)/, '') + '.' + fraction.padEnd(2, '0');
    return [{ line, expense: { fecha, descripcion, importe, moneda: currency } }];
  });
}
