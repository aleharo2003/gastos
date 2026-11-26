import { CategoryCatalog } from './category-catalog';
import { CategorySettings } from './category-settings';
import { SpaceExport } from './space-export';
import { ExpenseImport } from './expense-import';
import { TodayCategoryReport } from './today-category-report';
import { Movements } from './movements';
import { DueOverview } from './due-overview';
import { Commitments, type InstallmentReminder } from './commitments';
import { SavingsGoals, type GoalTransfer } from './savings-goals';
import { Transfers } from './transfers';
import { Incomes } from './incomes';
import { SavingsSummary } from './savings-summary';
import { ReminderPreferences } from './reminder-preferences';
import { Planning } from './planning';
import { Expenses, normalizeAmount, showAmount } from './expenses';
import { money, rateUnits, reference } from './money-reference';
import { ChangeDetectorRef, Component, computed, DestroyRef, effect, inject, Input, OnInit, signal, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { DOCUMENT } from '@angular/common';
import { AuthSession } from './auth-session';

const accountTypes = {
  efectivo: 'Efectivo', banco: 'Cuenta bancaria', billetera: 'Billetera virtual',
  tarjeta_credito: 'Tarjeta de crédito', inversion: 'Inversión',
} as const;
type AccountProfile = {
  tipo: keyof typeof accountTypes; moneda: 'ARS' | 'USD' | 'EUR'; saldo_inicial: string;
  dia_cierre?: number; dia_vencimiento?: number; fecha_vencimiento?: string; tasa_anual?: string;
};
type Account = { id: string; espacio_id: string; nombre: string } & Partial<AccountProfile>;
type NewAccount = { id: string; nombre: string } & AccountProfile;
type Page = { items: Account[]; next_offset: number | null };
type AccountBalance = { totales: { moneda: string; saldo: string }[] };

@Component({
  selector: 'app-accounts', imports: [FormsModule, CategorySettings, SpaceExport, ExpenseImport, TodayCategoryReport, Movements, Expenses, Planning, Incomes, Transfers, SavingsGoals, SavingsSummary, Commitments, DueOverview, ReminderPreferences],
  templateUrl: './accounts.html', styleUrl: './accounts.css',
})
export class Accounts implements OnInit {
  @Input({ required: true }) space = '';
  readonly installmentReminder = signal<InstallmentReminder | null>(null);
  private readonly document = inject(DOCUMENT);
  private readonly changeDetector = inject(ChangeDetectorRef);
  readonly items = signal<Account[]>([]);
  readonly movementAccount = signal<Account | null>(null);
  readonly movementReport = signal<{ desde: string; hasta: string; categoria: string; moneda: string } | null>(null);

  openCategoryHistory(report: { desde: string; hasta: string; categoria: string; moneda: string }): void {
    this.movementAccount.set(null);
    this.movementReport.set(report);
    this.tab.set('movements');
  }

  openAccountHistory(account: Account | null = null): void {
    this.movementReport.set(null);
    this.movementAccount.set(account);
    this.tab.set('movements');
  }

  readonly selected = signal<Account[]>([{id:'',espacio_id:'',nombre:'Todas las cuentas'}]);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly notice = signal('');
  readonly next = signal<number | null>(null);
  readonly tab = signal<'today' | 'expenses' | 'incomes' | 'movements' | 'accounts' | 'plan' | 'savings' | 'debts' | 'reminders'>(
    inject(DOCUMENT).defaultView?.matchMedia?.('(max-width: 767px)').matches ? 'expenses' : 'today',
  );
  readonly showInactive = signal(false);
  readonly inactiveAccounts = signal<Account[]>([]);
  readonly inactiveOffset = signal<number | null>(0);
  readonly inactiveLoading = signal(false);
  readonly changingState = signal<string | null>(null);
  readonly expandedBalance = signal<string | null>(null);
  readonly balance = signal<AccountBalance | null>(null);
  readonly balanceError = signal(false);
  readonly amountsHidden = signal(false);
  readonly balances = signal<AccountBalance | null>(null);
  readonly balancesError = signal(false);
  readonly balanceCurrency = signal<'ARS' | 'USD'>('ARS');
  readonly referenceRate = signal('');
  readonly consolidatedBalance = computed(() => {
    const balances = this.balances();
    if (!balances) return null;
    const currency = this.balanceCurrency();
    const rate = rateUnits(this.referenceRate());
    const positive = balances.totales.filter(row => !row.saldo.startsWith('-'))
      .map(row => ({ moneda: row.moneda, mes: row.saldo }));
    const negative = balances.totales.filter(row => row.saldo.startsWith('-'))
      .map(row => ({ moneda: row.moneda, mes: row.saldo.slice(1) }));
    const credit = reference(positive, 'mes', currency, rate);
    const debit = reference(negative, 'mes', currency, rate);
    if (credit === null || debit === null) return { value: null, estimated: false };
    return { value: credit - debit, estimated: [...positive, ...negative].some(row =>
      row.moneda !== currency && row.mes !== '0.00') };
  });

  @ViewChild(Commitments) commitments?: Commitments;
  @ViewChild(Expenses) expenses?: Expenses;
  private quickReturnTab?: ReturnType<typeof this.tab>;
  readonly quickNotice = signal(false);

  openQuickExpense(): void {
    if (!this.expenses || this.expenses.editing || this.expenses.saving()) return;
    if (this.tab() !== 'expenses' || !this.expenses.quickOpen()) this.quickReturnTab = this.tab();
    this.quickNotice.set(false);
    this.tab.set('expenses');
    this.expenses.openQuickEntry();
    this.changeDetector.detectChanges();
    this.document.getElementById('quick-expense-amount')?.focus();
  }

  finishQuickExpense(): void {
    const previous = this.quickReturnTab;
    this.quickReturnTab = undefined;
    if (!previous || previous === 'expenses') return;
    this.tab.set(previous);
    this.quickNotice.set(true);
  }

  async undoQuickExpense(): Promise<void> {
    await this.expenses?.undoSave();
    if (this.expenses?.error()) this.tab.set('expenses');
  }
  @ViewChild(Incomes) incomes?: Incomes;
  openIncome(): void {
    this.tab.set('incomes');
    this.incomes?.openEntry();
  }
  @ViewChild(Transfers) transfers?: Transfers;
  async fundGoal(goal: GoalTransfer): Promise<void> {
    if (!this.items().some(row => row.id === goal.cuenta_id)) {
      try {
        const account = await this.auth.accountRequest<Account & { activa: boolean }>(
          'GET', `${this.path}/${encodeURIComponent(goal.cuenta_id)}`,
        );
        if (!this.alive) return;
        if (!account.activa) {
          this.transfers?.error.set('La cuenta de la meta está inactiva. Reactivala desde Cuentas para hacer un aporte.');
          return;
        }
        this.items.update(rows => rows.some(row => row.id === account.id) ? rows : [...rows, account]);
      } catch {
        if (this.alive) this.transfers?.error.set('No pudimos consultar la cuenta de la meta.');
        return;
      }
    }
    this.transfers?.prepareGoal(goal);
  }
  choose(id: string): void {
    const account = id === '' ? {id:'',espacio_id:this.space,nombre:'Todas las cuentas'} : this.items().find(row => row.id === id);
    if (!account) return;
    if (this.selected()[0]?.id !== id) {
      if (this.expenses?.hasPendingWork() || this.incomes?.hasPendingWork()) {
        this.error.set('Terminá o limpiá el formulario de ingresos, gastos y comprobantes antes de cambiar de cuenta.');
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
  duePaymentSaved(): void {
    this.planRevision.update(this.incrementPlan);
    void this.expenses?.load();
    void this.commitments?.refreshPayments();
  }
  readonly draftCount=signal(0);
  readonly planRevision=signal(0);
  readonly incrementPlan=(value:number)=>value+1;
  readonly accountTypes = accountTypes;
  readonly accountTypeOptions = Object.entries(accountTypes);
  name = '';
  accountType: AccountProfile['tipo'] = 'efectivo';
  accountCurrency: AccountProfile['moneda'] = 'ARS';
  openingBalance = '';
  statementDay: number | null = null;
  cardDueDay: number | null = null;
  investmentDue = '';
  annualRate = '';
  readonly editingAccount = signal<Account | null>(null);
  readonly renameError = signal('');
  readonly renaming = signal(false);
  editedName = '';
  private readonly auth = inject(AuthSession);
  private alive = true;
  private pending?: NewAccount;
  private balanceRequest = 0;
  private balancesRequest = 0;
  private readonly rateListener = (event: Event) => {
    const detail = (event as CustomEvent).detail;
    if (detail?.space === this.space && typeof detail.rate === 'string') this.referenceRate.set(detail.rate);
  };
  private readonly privacyListener = (event: Event) => {
    this.amountsHidden.set((event as CustomEvent).detail === true);
  };

  constructor() {
    try { this.amountsHidden.set(localStorage.getItem('gastos.totals.hidden') === 'true'); } catch {}
    window.addEventListener('gastos-privacy', this.privacyListener);
    window.addEventListener('gastos-reference', this.rateListener);
    effect(() => {
      if (this.tab() === 'accounts') void this.loadBalances();
    });
    effect(() => {
      if (this.tab() !== 'accounts') this.closeBalance();
    });
    inject(DestroyRef).onDestroy(() => {
      this.alive = false;
      window.removeEventListener('gastos-privacy', this.privacyListener);
      window.removeEventListener('gastos-reference', this.rateListener);
    });
  }

  toggleBalance(id: string): void {
    if (this.expandedBalance() === id) {
      this.closeBalance();
      return;
    }
    this.expandedBalance.set(id);
    void this.loadBalance(id);
  }

  async loadBalance(id: string): Promise<void> {
    const request = ++this.balanceRequest;
    this.balance.set(null);
    this.balanceError.set(false);
    try {
      const result = await this.auth.accountRequest<AccountBalance>(
        'GET', `/api/spaces/${encodeURIComponent(this.space)}/account-balance?account=${encodeURIComponent(id)}`,
      );
      if (!Array.isArray(result?.totales)) throw new Error('Saldo inválido');
      if (this.alive && request === this.balanceRequest) this.balance.set(result);
    } catch {
      if (this.alive && request === this.balanceRequest) this.balanceError.set(true);
    }
  }

  async loadBalances(): Promise<void> {
    const request = ++this.balancesRequest;
    this.balances.set(null);
    this.balancesError.set(false);
    try {
      const result = await this.auth.accountRequest<AccountBalance>(
        'GET', `/api/spaces/${encodeURIComponent(this.space)}/account-balance`,
      );
      if (!Array.isArray(result?.totales)) throw new Error('Saldos inválidos');
      if (this.alive && request === this.balancesRequest) this.balances.set(result);
    } catch {
      if (this.alive && request === this.balancesRequest) this.balancesError.set(true);
    }
  }

  formattedConsolidatedBalance(value: bigint): string {
    return value < 0n ? '−' + money(-value) : money(value);
  }

  private closeBalance(): void {
    this.balanceRequest++;
    this.expandedBalance.set(null);
    this.balance.set(null);
    this.balanceError.set(false);
  }

  balanceAmount(value: string): string {
    return this.amountsHidden() ? '••••' : showAmount(value);
  }
  private readonly categoryCatalog = inject(CategoryCatalog);

  ngOnInit(): void {
    const query = new URLSearchParams(this.document.location?.search ?? '');
    const month = query.get('mes');
    const action = query.get('aviso');
    const quota = query.get('cuota');
    if (query.get('espacio') === this.space && month && /^(?!0000)\d{4}-(0[1-9]|1[0-2])$/.test(month)) {
      if (action === 'pago' && quota && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(quota)) {
        this.installmentReminder.set({ month, action, quota });
      } else if (action === 'importe' || action === 'ajuste') {
        this.installmentReminder.set({ month, action });
      }
      if (this.installmentReminder()) this.tab.set('debts');
    }
    this.categoryCatalog.ensure(this.space);
    try {
      const saved = JSON.parse(localStorage.getItem('gastos.reference.' + this.space) ?? 'null');
      if (typeof saved?.rate === 'string') this.referenceRate.set(saved.rate);
    } catch {}
    void this.load();
  }
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
      const expanded = this.expandedBalance();
      if (!more && expanded) {
        if (rows.some(account => account.id === expanded)) void this.loadBalance(expanded);
        else this.closeBalance();
      }
    } catch {
      if (this.alive) this.error.set('No pudimos cargar tus cuentas. Volvé a intentar.');
    } finally { if (this.alive) this.loading.set(false); }
  }

  toggleInactive(): void {
    this.showInactive.update(show => !show);
    if (this.showInactive()) void this.loadInactive();
  }

  async loadInactive(more = false): Promise<void> {
    const offset = more ? this.inactiveOffset() : 0;
    if (offset === null || this.inactiveLoading()) return;
    this.inactiveLoading.set(true);
    this.error.set('');
    try {
      const page = await this.auth.accountRequest<Page>('GET', `${this.path}?offset=${offset}&inactivas=true`);
      if (!this.alive) return;
      this.inactiveAccounts.update(rows => [...new Map((more ? [...rows, ...page.items] : page.items).map(row => [row.id, row])).values()]);
      this.inactiveOffset.set(page.next_offset);
    } catch {
      if (this.alive) this.error.set('No pudimos cargar las cuentas inactivas.');
    } finally {
      if (this.alive) this.inactiveLoading.set(false);
    }
  }

  async setAccountActive(account: Account, active: boolean): Promise<void> {
    if (this.changingState() || this.loading() || this.inactiveLoading() || this.renaming()) return;
    if (!active && (this.expenses?.hasPendingWork() || this.incomes?.hasPendingWork())) {
      this.error.set('Terminá o limpiá los formularios abiertos antes de desactivar la cuenta.');
      return;
    }
    this.changingState.set(account.id);
    this.error.set('');
    this.notice.set('');
    try {
      const updated = await this.auth.accountRequest<Account & { activa: boolean }>(
        'PATCH', `${this.path}/${encodeURIComponent(account.id)}/status`, { activa: active },
      );
      if (!this.alive) return;
      if (updated.activa) {
        this.inactiveAccounts.update(rows => rows.filter(row => row.id !== account.id));
      } else {
        this.items.update(rows => rows.filter(row => row.id !== account.id));
        if (this.expandedBalance() === account.id) this.closeBalance();
        if (this.editingAccount()?.id === account.id) this.closeAccountEditor();
        if (this.selected()[0]?.id === account.id) {
          this.selected.set([{ id: '', espacio_id: this.space, nombre: 'Todas las cuentas' }]);
        }
      }
      this.notice.set(active ? 'Cuenta reactivada.' : 'Cuenta desactivada. Su historial se conserva.');
      await Promise.all([this.load(), this.showInactive() ? this.loadInactive() : Promise.resolve()]);
    } catch (error) {
      if (this.alive) this.error.set(error instanceof HttpErrorResponse && error.status === 403
        ? 'No tenés permiso para cambiar el estado de esta cuenta.'
        : 'No pudimos confirmar el cambio de estado. Podés reintentar.');
    } finally {
      if (this.alive) this.changingState.set(null);
    }
  }

  editAccount(account: Account): void {
    if (this.renaming()) return;
    this.editingAccount.set(account);
    this.editedName = account.nombre;
    this.renameError.set('');
    this.notice.set('');
  }

  closeAccountEditor(): void {
    if (this.renaming()) return;
    this.editingAccount.set(null);
    this.renameError.set('');
  }

  async renameAccount(): Promise<void> {
    const account = this.editingAccount();
    const nombre = this.editedName.trim();
    if (!account || this.renaming() || !nombre || [...nombre].length > 80 || nombre === account.nombre) return;
    this.renaming.set(true);
    this.renameError.set('');
    try {
      const updated = await this.auth.accountRequest<Account>('PATCH', `${this.path}/${encodeURIComponent(account.id)}`,
        { nombre, nombre_anterior: account.nombre });
      if (!this.alive) return;
      this.items.update(rows => rows.map(row => row.id === updated.id ? updated : row));
      if (this.selected()[0]?.id === updated.id) this.selected.set([updated]);
      this.editingAccount.set(null);
      this.notice.set('Nombre de la cuenta actualizado.');
    } catch (error) {
      if (!this.alive) return;
      const status = error instanceof HttpErrorResponse ? error.status : 0;
      if (status === 409) {
        this.renameError.set('Otra sesión cambió el nombre. Actualizá la lista, cerrá este formulario y volvé a editar la cuenta.');
      } else if (status === 403) {
        this.renameError.set('No tenés permiso para editar esta cuenta.');
      } else {
        this.renameError.set('No pudimos confirmar el cambio. Podés reintentar.');
      }
    } finally {
      if (this.alive) this.renaming.set(false);
    }
  }

  async save(): Promise<void> {
    const name = this.name.trim();
    if (this.saving() || this.loading() || !name || [...name].length > 80) return;
    this.error.set(''); this.notice.set('');
    const profile = this.accountProfile();
    if (!profile) return;
    this.saving.set(true);
    const values = { nombre: name, ...profile };
    if (!this.pending || Object.keys(this.pending).length !== Object.keys(values).length + 1
      || Object.entries(values).some(([key, value]) => this.pending?.[key as keyof NewAccount] !== value)) {
      this.pending = { id: crypto.randomUUID(), ...values };
    }
    try {
      const row = await this.auth.accountRequest<Account>('POST', this.path, this.pending);
      if (!this.alive) return;
      this.items.update(items => [...items.filter(item => item.id !== row.id), row]);
      this.pending = undefined;
      this.name = '';
      this.openingBalance = '';
      this.statementDay = null;
      this.cardDueDay = null;
      this.investmentDue = '';
      this.annualRate = '';
      this.notice.set('Cuenta guardada.');
      this.planRevision.update(this.incrementPlan);
      if (this.tab() === 'accounts') {
        this.toggleBalance(row.id);
        void this.loadBalances();
      }
    } catch (error) {
      if (this.alive) this.error.set(error instanceof HttpErrorResponse && error.status === 403
        ? 'No tenés permiso para crear cuentas en este espacio.'
        : 'No pudimos confirmar el guardado. Reintentá con los mismos datos; no se duplicará esta solicitud.');
    } finally { if (this.alive) this.saving.set(false); }
  }
  private accountProfile(): AccountProfile | null {
    const rawAmount = this.openingBalance.trim();
    const amount = normalizeAmount(rawAmount.replace(/^-/, ''));
    const isZero = rawAmount === '' || /^-?0+(?:[.,]0{1,2})?$/.test(rawAmount);
    if (!isZero && !amount) {
      this.error.set('Ingresá el saldo inicial con hasta dos decimales y sin separador de miles.');
      return null;
    }
    const profile: AccountProfile = {
      tipo: this.accountType, moneda: this.accountCurrency,
      saldo_inicial: isZero ? '0.00' : (rawAmount.startsWith('-') ? '-' : '') + amount,
    };
    if (profile.tipo === 'tarjeta_credito') {
      const validDay = (day: number | null): day is number => day !== null && Number.isInteger(day) && day >= 1 && day <= 31;
      if (!validDay(this.statementDay) || !validDay(this.cardDueDay)) {
        this.error.set('Ingresá el día de cierre y el día de vencimiento, entre 1 y 31.');
        return null;
      }
      profile.dia_cierre = this.statementDay;
      profile.dia_vencimiento = this.cardDueDay;
    }
    if (profile.tipo === 'inversion') {
      const rate = this.annualRate.trim().replace(',', '.');
      if (isZero || rawAmount.startsWith('-') || !this.investmentDue || !/^(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{1,4})?$/.test(rate)) {
        this.error.set('Ingresá un capital positivo, una fecha y una tasa anual válida.');
        return null;
      }
      profile.fecha_vencimiento = this.investmentDue;
      profile.tasa_anual = rate;
    }
    return profile;
  }
}
