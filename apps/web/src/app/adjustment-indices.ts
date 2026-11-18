import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, ElementRef, inject, Input, OnChanges, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AuthSession } from './auth-session';

type IndexValue = { indice: string; periodo: string; variacion: string };
type IndexImport = { importadas: number; existentes: number };
type IndexPage = { items: IndexValue[]; next_offset: number | null };

@Component({
  selector: 'app-adjustment-indices',
  imports: [FormsModule],
  templateUrl: './adjustment-indices.html',
  styleUrl: './commitments.css',
})
export class AdjustmentIndices implements OnChanges {
  @Input({ required: true }) space = '';

  private readonly auth = inject(AuthSession);
  private readonly destroy = inject(DestroyRef);
  private generation = 0;
  private readonly csvInput = viewChild<ElementRef<HTMLInputElement>>('csvInput');

  protected indice = '';
  protected periodo = '';
  protected variacion = '';
  protected readonly items = signal<IndexValue[]>([]);
  protected readonly nextOffset = signal<number | null>(null);
  protected readonly loading = signal(false);
  protected readonly saving = signal(false);
  protected readonly loaded = signal(false);
  protected readonly listError = signal('');
  protected readonly importError = signal('');
  protected readonly saveError = signal('');
  protected readonly notice = signal('');

  ngOnChanges(): void {
    this.generation++;
    const csvInput = this.csvInput()?.nativeElement;
    if (csvInput) csvInput.value = '';
    this.indice = this.periodo = this.variacion = '';
    this.items.set([]);
    this.nextOffset.set(null);
    this.loading.set(false);
    this.saving.set(false);
    this.loaded.set(false);
    this.listError.set('');
    this.saveError.set('');
    this.importError.set('');
    this.notice.set('');
    if (this.space) void this.load();
  }

  private get path(): string {
    return '/api/spaces/' + encodeURIComponent(this.space) + '/index-values';
  }

  private active(generation: number): boolean {
    return !this.destroy.destroyed && generation === this.generation;
  }

  protected async load(offset = 0): Promise<void> {
    if (this.loading()) return;
    const generation = this.generation;
    this.loading.set(true);
    this.listError.set('');
    try {
      const page = await this.auth.accountRequest<IndexPage>('GET', this.path + '?offset=' + offset);
      if (!this.active(generation)) return;
      this.items.set(offset === 0 ? page.items : [...this.items(), ...page.items]);
      this.nextOffset.set(page.next_offset);
      this.loaded.set(true);
    } catch {
      if (this.active(generation)) this.listError.set('No se pudieron cargar las variaciones.');
    } finally {
      if (this.active(generation)) this.loading.set(false);
    }
  }

  protected async save(): Promise<void> {
    if (this.saving() || this.loading()) return;
    this.saveError.set('');
    this.importError.set('');
    this.notice.set('');
    const indice = this.indice.trim();
    const periodo = this.periodo;
    const variacion = this.variacion.trim().replace(',', '.');
    if (!indice || [...indice].length > 80 || !/^(?!0000)[0-9]{4}-(0[1-9]|1[0-2])$/.test(periodo) ||
        !/^-?[0-9]{1,6}(\.[0-9]{1,4})?$/.test(variacion) || Number(variacion) <= -100) {
      this.saveError.set('Ingresá un nombre, un mes válido y un porcentaje mayor a −100 con hasta cuatro decimales.');
      return;
    }
    const generation = this.generation;
    this.saving.set(true);
    try {
      await this.auth.accountRequest<IndexValue>('POST', this.path, { indice, periodo, variacion });
      if (!this.active(generation)) return;
      this.notice.set('Variación guardada.');
      this.variacion = '';
      await this.load();
    } catch (error) {
      if (!this.active(generation)) return;
      const status = error instanceof HttpErrorResponse ? error.status : 0;
      this.saveError.set(status === 409 ? 'Ese índice ya tiene otra variación para el mes indicado.' :
        status === 403 ? 'Tu rol en el espacio no permite guardar variaciones.' :
        'No se pudo guardar la variación.');
    } finally {
      if (this.active(generation)) this.saving.set(false);
    }
  }

  protected async importCsv(input: HTMLInputElement): Promise<void> {
    if (this.saving() || this.loading()) return;
    this.importError.set('');
    this.saveError.set('');
    this.notice.set('');
    const file = input.files?.[0];
    if (!file || !file.size || file.size > 32 * 1024) {
      this.importError.set('Seleccioná un CSV con datos de hasta 32 KiB.');
      return;
    }

    const generation = this.generation;
    this.saving.set(true);
    try {
      let csv: string;
      try {
        csv = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer());
      } catch {
        if (this.active(generation)) this.importError.set('El archivo debe poder leerse como CSV UTF-8.');
        return;
      }
      if (!this.active(generation)) return;
      const result = await this.auth.accountRequest<IndexImport>('POST', this.path + '/import', { csv });
      if (!this.active(generation)) return;
      input.value = '';
      this.notice.set(`Importadas: ${result.importadas}. Ya registradas: ${result.existentes}.`);
      await this.load();
    } catch (error) {
      if (!this.active(generation)) return;
      if (error instanceof HttpErrorResponse) {
        const message = error.error?.message;
        if ([409, 422].includes(error.status) && typeof message === 'string') {
          this.importError.set(message);
          return;
        }
        if (error.status === 403) {
          this.importError.set('Tu rol en el espacio no permite importar variaciones.');
          return;
        }
      }
      this.importError.set('No se pudo importar el CSV.');
    } finally {
      if (this.active(generation)) this.saving.set(false);
    }
  }
}
