import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, computed, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AuthSession } from './auth-session';
import { ImportMapping, ImportRow, MAX_CSV_BYTES, parseImportCsv, previewImport } from './expense-import-csv';

type Batch = { lote: string; gastos: number; fecha: string };
type Checked = { nuevas: number; duplicadas: number[]; coincidencias_manuales: number[]; revision: string };
const movementLabels = { gasto: 'gastos', ingreso: 'ingresos', transferencia: 'transferencias' };

@Component({
  selector: 'app-expense-import',
  imports: [FormsModule],
  templateUrl: './expense-import.html',
})
export class ExpenseImport {
  readonly space = input.required<string>();
  readonly accounts = input<readonly { id: string; nombre: string }[]>([]);
  readonly moreAccounts = input(false);
  readonly loadAccounts = output<void>();
  readonly changed = output<void>();
  readonly headers = signal<string[]>([]);
  readonly rows = signal<ImportRow[]>([]);
  readonly error = signal('');
  readonly notice = signal('');
  readonly busy = signal(false);
  readonly checked = signal<Checked | null>(null);
  readonly batches = signal<Batch[]>([]);
  readonly invalidCount = computed(() => this.rows().filter(row => row.error).length);
  readonly validRows = computed(() => this.rows().filter(row => !!row.expense));
  readonly valid = computed(() => this.validRows().map(row => row.expense!));
  readonly duplicates = computed(() => this.lineNumbers(this.checked()?.duplicadas));
  readonly manualMatches = computed(() => this.lineNumbers(this.checked()?.coincidencias_manuales));
  account = '';
  destination = '';
  kind: keyof typeof movementLabels = 'gasto';
  get movementLabel() { return movementLabels[this.kind]; }
  get accountsReady(): boolean {
    return !!this.account && (this.kind !== 'transferencia' || (!!this.destination && this.account !== this.destination));
  }
  skipInvalid = false;
  includeManualMatches = false;
  private batch = '';
  private readonly auth = inject(AuthSession);
  private readonly destroy = inject(DestroyRef);
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
    this.invalidate();
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
    this.invalidate();
    this.rows.set(previewImport(this.records, this.headers().length, this.mapping, this.currency));
  }

  invalidate(): void {
    this.checked.set(null);
    this.notice.set('');
    this.batch = '';
    this.skipInvalid = false;
    this.includeManualMatches = false;
  }

  private lineNumbers(indices: number[] | undefined): number[] {
    return indices?.map(index => this.validRows()[index]?.line).filter(line => line !== undefined) ?? [];
  }

  private path(suffix = ''): string {
    const base = '/api/spaces/' + encodeURIComponent(this.space()) + '/accounts/' + encodeURIComponent(this.account);
    const query = new URLSearchParams({ tipo: this.kind });
    if (this.kind === 'transferencia') query.set('destino', this.destination);
    return base + '/expense-import' + suffix + '?' + query;
  }

  async chooseAccount(): Promise<void> {
    this.invalidate();
    this.batches.set([]);
    if (this.accountsReady) await this.run(() => this.loadBatches());
  }

  private async loadBatches(): Promise<void> {
    const page = await this.auth.accountRequest<{ items: Batch[] }>('GET', this.path());
    this.batches.set(page.items);
  }

  async check(includeManualMatches = false): Promise<void> {
    if (!this.accountsReady || !this.valid().length || (this.invalidCount() && !this.skipInvalid)) return;
    await this.run(async () => {
      const result = await this.auth.accountRequest<Checked>('POST', this.path('/preview'), {
        filas: this.valid(), incluir_coincidencias_manuales: includeManualMatches,
      });
      this.batch = crypto.randomUUID();
      this.includeManualMatches = includeManualMatches;
      this.checked.set(result);
    });
  }

  async commit(): Promise<void> {
    const checked = this.checked();
    if (!checked?.nuevas || !this.batch) return;
    const payload = {
      filas: this.valid(), lote: this.batch, revision: checked.revision,
      incluir_coincidencias_manuales: this.includeManualMatches,
    };
    await this.run(async () => {
      const result = await this.auth.accountRequest<{ importadas: number }>('POST', this.path(), payload);
      this.checked.set(null);
      this.notice.set('Movimientos importados: ' + result.importadas + '.');
      if (this.destroy.destroyed) return;
      this.changed.emit();
      await this.loadBatches();
    });
  }

  async undo(batch: Batch): Promise<void> {
    if (this.busy() || !window.confirm('¿Anular los movimientos vigentes de este lote?')) return;
    await this.run(async () => {
      const result = await this.auth.accountRequest<{ anuladas: number }>(
        'POST', this.path('/' + encodeURIComponent(batch.lote) + '/void'),
      );
      this.invalidate();
      this.notice.set('Movimientos anulados: ' + result.anuladas + '.');
      if (this.destroy.destroyed) return;
      this.changed.emit();
      await this.loadBatches();
    });
  }

  private async run(operation: () => Promise<void>): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    this.error.set('');
    try {
      await operation();
    } catch (error) {
      const status = error instanceof HttpErrorResponse ? error.status : 0;
      if (status === 409) {
        this.checked.set(null);
        this.error.set('Revisá que la cuenta esté activa y volvé a comprobar los duplicados.');
      } else if (status === 413) this.error.set('El lote supera el tamaño permitido. Dividí el archivo en partes.');
      else if (status === 403) this.error.set('No tenés permiso para importar en esta cuenta.');
      else this.error.set('No pudimos completar la operación. Volvé a intentar.');
    } finally {
      this.busy.set(false);
    }
  }
}
