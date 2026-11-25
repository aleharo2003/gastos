import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ImportMapping, ImportRow, MAX_CSV_BYTES, parseImportCsv, previewImport } from './expense-import-csv';

@Component({
  selector: 'app-expense-import',
  imports: [FormsModule],
  templateUrl: './expense-import.html',
})
export class ExpenseImport {
  readonly headers = signal<string[]>([]);
  readonly rows = signal<ImportRow[]>([]);
  readonly error = signal('');
  readonly fields = [
    { key: 'fecha', label: 'Fecha' }, { key: 'descripcion', label: 'Descripción' }, { key: 'importe', label: 'Importe' },
  ] as const;
  mapping: ImportMapping = { fecha: -1, descripcion: -1, importe: -1 };
  currency = 'ARS';
  separator: ',' | ';' = ';';
  private raw = '';
  private records: string[][] = [];
  private readVersion = 0;

  async select(event: Event): Promise<void> {
    const file = (event.target as HTMLInputElement).files?.[0];
    const version = ++this.readVersion;
    this.raw = '';
    this.parse();
    if (!file) return;
    if (file.size > MAX_CSV_BYTES) {
      this.error.set('El archivo supera 256 KB. Dividilo en archivos más chicos.');
      return;
    }
    try {
      const bytes = await file.arrayBuffer();
      if (version !== this.readVersion) return;
      this.raw = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
      this.parse();
    } catch {
      if (version === this.readVersion) this.error.set('Abrí el archivo en Excel y guardalo como CSV UTF-8.');
    }
  }

  parse(): void {
    this.headers.set([]);
    this.rows.set([]);
    this.records = [];
    this.error.set('');
    if (!this.raw) return;
    try {
      const { headers, records } = parseImportCsv(this.raw, this.separator);
      this.headers.set(headers);
      this.records = records;
      const keys = headers.map(header => header.trim().normalize('NFD').replace(/\p{M}/gu, '').toLowerCase());
      this.mapping = {
        fecha: keys.indexOf('fecha'), descripcion: keys.indexOf('descripcion'),
        importe: keys.findIndex(key => key === 'importe' || key === 'monto'),
      };
      this.refresh();
    } catch (error) {
      this.error.set(error instanceof Error ? error.message : 'No pudimos leer el CSV.');
    }
  }

  refresh(): void {
    this.rows.set(previewImport(this.records, this.headers().length, this.mapping, this.currency));
  }
}
