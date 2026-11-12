import { Planning } from './planning';
import { Expenses } from './expenses';
import { Component, DestroyRef, inject, Input, OnInit, signal, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthSession } from './auth-session';

type Account = { id: string; espacio_id: string; nombre: string };
type Page = { items: Account[]; next_offset: number | null };

@Component({
  selector: 'app-accounts', imports: [FormsModule, Expenses, Planning],
  templateUrl: './accounts.html', styleUrl: './accounts.css',
})
export class Accounts implements OnInit {
  @Input({ required: true }) space = '';
  readonly items = signal<Account[]>([]);
  readonly selected = signal<Account[]>([{id:'',espacio_id:'',nombre:'Todas las cuentas'}]);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly notice = signal('');
  readonly next = signal<number | null>(null);
  readonly tab = signal<'expenses' | 'accounts' | 'plan'>('expenses');
  @ViewChild(Expenses) expenses?: Expenses;
  choose(id: string): void {
    const account = id === '' ? {id:'',espacio_id:this.space,nombre:'Todas las cuentas'} : this.items().find(row => row.id === id);
    if (!account) return;
    if (this.selected()[0]?.id !== id) {
      if (this.expenses?.hasPendingWork()) {
        this.error.set('Terminá o cancelá el formulario y los comprobantes antes de cambiar de cuenta.');
        return;
      }
      this.selected.set([account]);
    }
    this.error.set(''); this.tab.set('expenses');
  }
  selectAccount(event: Event): void {
    const select = event.target as HTMLSelectElement;
    this.choose(select.value);
    select.value = this.selected()[0]?.id ?? '';
  }
  readonly planRevision=signal(0);
  readonly incrementPlan=(value:number)=>value+1;
  name = '';
  private readonly auth = inject(AuthSession);
  private alive = true;
  private pending?: { id: string; nombre: string };
  constructor() { inject(DestroyRef).onDestroy(() => { this.alive = false; }); }
  ngOnInit(): void { void this.load(); }
  private get path() { return `/api/spaces/${encodeURIComponent(this.space)}/accounts`; }

  async load(more = false): Promise<void> {
    if (this.loading() || this.saving()) return;
    const offset = more ? this.next() : 0;
    if (offset === null) return;
    this.loading.set(true); this.error.set('');
    try {
      const page = await this.auth.accountRequest<Page>('GET', `${this.path}?offset=${offset}`);
      if (!this.alive) return;
      const rows = more ? [...this.items(), ...page.items] : page.items;
      this.items.set([...new Map(rows.map(row => [row.id, row])).values()]);
      this.next.set(page.next_offset);

    } catch {
      if (this.alive) this.error.set('No pudimos cargar tus cuentas. Volvé a intentar.');
    } finally { if (this.alive) this.loading.set(false); }
  }

  async save(): Promise<void> {
    const name = this.name.trim();
    if (this.saving() || this.loading() || !name || [...name].length > 80) return;
    this.saving.set(true); this.error.set(''); this.notice.set('');
    if (!this.pending || this.pending.nombre !== name) this.pending = { id: crypto.randomUUID(), nombre: name };
    try {
      const row = await this.auth.accountRequest<Account>('POST', this.path, this.pending);
      if (!this.alive) return;
      this.items.update(items => [...items.filter(item => item.id !== row.id), row]);
      this.pending = undefined; this.name = '';
      this.notice.set('Cuenta guardada.');
    } catch (error) {
      if (this.alive) this.error.set(error instanceof HttpErrorResponse && error.status === 403
        ? 'No tenés permiso para crear cuentas en este espacio.'
        : 'No pudimos confirmar el guardado. Reintentá con el mismo nombre; no se duplicará esta solicitud.');
    } finally { if (this.alive) this.saving.set(false); }
  }
}
