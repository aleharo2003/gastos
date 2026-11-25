import { DOCUMENT } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, input, signal } from '@angular/core';
import { AuthSession } from './auth-session';

@Component({
  selector: 'app-space-export',
  template: `
    <section class="workspace-panel" aria-labelledby="space-export-title">
      <h3 id="space-export-title">Exportar mis datos</h3>
      <p>Descargá un ZIP con tus cuentas, movimientos, categorías y otros datos del espacio en archivos CSV. De los comprobantes se exporta la información del archivo.</p>
      <button type="button" class="secondary" (click)="download()" [disabled]="loading()">
        Descargar ZIP de datos
      </button>
      @if (loading()) { <p role="status">Preparando el archivo.</p> }
      @if (success()) { <p role="status">Descarga iniciada.</p> }
      @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
    </section>
  `,
})
export class SpaceExport {
  readonly space = input.required<string>();
  readonly loading = signal(false);
  readonly success = signal(false);
  readonly error = signal('');
  private readonly auth = inject(AuthSession);
  private readonly document = inject(DOCUMENT);
  private readonly destroy = inject(DestroyRef);

  async download(): Promise<void> {
    if (this.loading()) return;
    const space = this.space();
    this.loading.set(true);
    this.success.set(false);
    this.error.set('');
    try {
      const archive = await this.auth.downloadSpaceExport(space);
      if (this.destroy.destroyed || this.space() !== space) return;
      if (archive.type !== 'application/zip' || archive.size < 22) throw new Error('Archivo inválido');
      const url = URL.createObjectURL(archive);
      const link = this.document.createElement('a');
      try {
        link.href = url;
        link.download = 'piggo-datos.zip';
        this.document.body.appendChild(link);
        link.click();
        this.success.set(true);
      } finally {
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1_000);
      }
    } catch (error) {
      if (this.destroy.destroyed || this.space() !== space) return;
      const status = error instanceof HttpErrorResponse ? error.status : 0;
      if (status === 403) this.error.set('Solo el titular del espacio puede descargar los datos.');
      else if (status === 413) this.error.set('Los datos superan el tamaño permitido para esta descarga.');
      else this.error.set('No pudimos descargar los datos. Volvé a intentar.');
    } finally {
      if (!this.destroy.destroyed) this.loading.set(false);
    }
  }
}
