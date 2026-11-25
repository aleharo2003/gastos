import { Injectable, inject, signal } from '@angular/core';
import { AuthSession } from './auth-session';
import { EXPENSE_CATEGORIES } from './expense-categories';

export type CategoryKind = 'gasto' | 'ingreso';
export type MovementCategory = {
  id: string; tipo: CategoryKind; nombre: string; activa: boolean; color: string | null;
};

const expenseDefaults: MovementCategory[] = EXPENSE_CATEGORIES.map(({ id, label }) => ({
  id, tipo: 'gasto', nombre: label, activa: true, color: null,
}));

export function categoryPath(space: string): string {
  return '/api/spaces/' + encodeURIComponent(space) + '/categories';
}

@Injectable({ providedIn: 'root' })
export class CategoryCatalog {
  private readonly auth = inject(AuthSession);
  private readonly snapshots = signal(new Map<string, readonly MovementCategory[]>());
  private readonly requests = new Map<string, number>();
  private version = 0;

  private key(space: string): string {
    return (this.auth.userId ?? '') + ':' + space;
  }

  categories(space: string, kind?: CategoryKind): readonly MovementCategory[] {
    const rows = this.snapshots().get(this.key(space)) ?? expenseDefaults;
    return kind ? rows.filter(row => row.tipo === kind) : rows;
  }

  expenseOptions(space: string, activeOnly = false, selected = ''): { id: string; label: string }[] {
    return this.categories(space, 'gasto')
      .filter(row => !activeOnly || row.activa || row.id === selected)
      .map(row => ({ id: row.id, label: row.nombre + (activeOnly && !row.activa ? ' (inactiva)' : '') }));
  }

  label(space: string, kind: CategoryKind, id?: string | null): string {
    if (!id) return 'Sin categoría';
    return this.categories(space, kind).find(row => row.id === id)?.nombre ?? 'Categoría no disponible';
  }

  ensure(space: string): void {
    const key = this.key(space);
    if (!space || !this.auth.userId || this.snapshots().has(key) || this.requests.has(key)) return;
    void this.refresh(space).catch(() => {});
  }

  async refresh(space: string): Promise<void> {
    const key = this.key(space);
    const request = ++this.version;
    this.requests.set(key, request);
    try {
      const page = await this.auth.accountRequest<{ items: MovementCategory[] }>('GET', categoryPath(space));
      if (this.requests.get(key) !== request) return;
      this.snapshots.update(values => new Map(values).set(key, page.items));
    } finally {
      if (this.requests.get(key) === request) this.requests.delete(key);
    }
  }
}
