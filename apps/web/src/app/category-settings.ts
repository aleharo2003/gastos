import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AuthSession } from './auth-session';
import { CategoryCatalog, CategoryKind, MovementCategory, categoryPath } from './category-catalog';

@Component({
  selector: 'app-category-settings',
  imports: [FormsModule],
  templateUrl: './category-settings.html',
})
export class CategorySettings implements OnInit {
  readonly space = input.required<string>();
  readonly busy = signal(false);
  readonly ready = signal(false);
  readonly error = signal('');
  readonly duplicate = signal<MovementCategory | null>(null);
  private readonly auth = inject(AuthSession);
  private readonly catalog = inject(CategoryCatalog);
  private pending?: { id: string; kind: CategoryKind; name: string; color: string };
  kind: CategoryKind = 'gasto';
  name = '';
  color = '#64748b';
  editing: MovementCategory | null = null;

  ngOnInit(): void { void this.load(); }

  rows(): readonly MovementCategory[] {
    return this.catalog.categories(this.space(), this.kind);
  }

  async load(): Promise<void> {
    this.busy.set(true);
    this.error.set('');
    try {
      await this.catalog.refresh(this.space());
      this.ready.set(true);
    } catch {
      this.error.set('No pudimos cargar las categorías.');
    } finally {
      this.busy.set(false);
    }
  }

  reset(): void {
    this.name = '';
    this.color = '#64748b';
    this.editing = null;
    this.pending = undefined;
    this.duplicate.set(null);
    this.error.set('');
  }

  edit(row: MovementCategory): void {
    this.reset();
    this.editing = row;
    this.name = row.nombre;
    this.color = row.color ?? '#64748b';
  }

  async save(): Promise<void> {
    const name = this.name.trim();
    if (!name || this.busy()) return;
    const current = this.editing;
    if (current) {
      await this.change(current, name, this.color, current.activa);
      return;
    }
    if (!this.pending || this.pending.kind !== this.kind || this.pending.name !== name || this.pending.color !== this.color) {
      this.pending = { id: crypto.randomUUID(), kind: this.kind, name, color: this.color };
    }
    await this.write('POST', categoryPath(this.space()),
      { id: this.pending.id, tipo: this.kind, nombre: name, color: this.color }, name);
  }

  async toggle(row: MovementCategory): Promise<void> {
    if (!this.busy()) await this.change(row, row.nombre, row.color, !row.activa);
  }

  private async change(row: MovementCategory, name: string, color: string | null, active: boolean): Promise<void> {
    const url = categoryPath(this.space()) + '/' + row.tipo + '/' + encodeURIComponent(row.id);
    await this.write('PATCH', url, { nombre: name, color, activa: active }, name);
  }

  private async write(method: 'POST' | 'PATCH', url: string, body: unknown, name: string): Promise<void> {
    this.busy.set(true);
    this.error.set('');
    this.duplicate.set(null);
    try {
      await this.auth.accountRequest<MovementCategory>(method, url, body);
      this.reset();
      await this.catalog.refresh(this.space());
    } catch (error) {
      if (error instanceof HttpErrorResponse && error.status === 409) {
        const normalized = (value: string) => value.toLocaleLowerCase('es').replace(/\s+/g, '');
        this.duplicate.set(this.rows().find(row => row.id !== this.editing?.id && normalized(row.nombre) === normalized(name)) ?? null);
        this.error.set('Ya existe una categoría con ese nombre.');
      } else {
        this.error.set(error instanceof HttpErrorResponse && error.status === 403
          ? 'No tenés permiso para editar las categorías.'
          : 'No pudimos actualizar las categorías. Volvé a intentar.');
      }
    } finally {
      this.busy.set(false);
    }
  }
}
