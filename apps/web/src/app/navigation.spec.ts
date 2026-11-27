import { Commitments } from './commitments';
import { By } from '@angular/platform-browser';
import { Transfers } from './transfers';
import { TestBed } from '@angular/core/testing';
import { Accounts } from './accounts';
import { AuthSession } from './auth-session';

describe('Navegación del espacio', () => {
  async function setup(withCategoryAlerts = false, withBudgetNotice = false) {
    let budgetNotice = withBudgetNotice;
    const accounts = [{id:'one',espacio_id:'s',nombre:'Efectivo'}, {id:'two',espacio_id:'s',nombre:'Banco'}];
    TestBed.configureTestingModule({imports:[Accounts],providers:[{provide:AuthSession,useValue:{
      accountRequest: async (method:string,path:string) => {
        if (path.endsWith('/spending-plan/alerts')) {
          if (method === 'POST') budgetNotice = false;
          return { items: budgetNotice ? [
            { id: 'one-notice', periodo: 'semanal', desde: '2026-11-23', categoria: '', moneda: 'ARS', exceso: '25.00' },
          ] : [] };
        }
        return withCategoryAlerts && path.endsWith('/spending-plan') ? ({
        version: 1, datos: { limites: { diario: null, semanal: null }, conceptos: [],
          limites_categoria: ['alimentos', 'ocio', 'salud'].map(categoria => ({ categoria, moneda: 'ARS', importe: '100.00' })) },
      }) : withCategoryAlerts && path.endsWith('/expense-category-summary') ? ({
        desde: '2026-11-01', hasta: '2026-11-30', items: [
          { categoria: 'alimentos', moneda: 'ARS', total: '80.00' },
          { categoria: 'ocio', moneda: 'ARS', total: '125.00' },
          { categoria: 'salud', moneda: 'ARS', total: '50.00' },
        ],
      }) : path.endsWith('/due-overview') ? ({fecha:'2026-11-17',fin_semana:'2026-11-22',grupos:{hoy:{cantidad:0,totales:[],items:[]},semana:{cantidad:0,totales:[],items:[]},vencidas:{cantidad:0,totales:[],items:[]}},resumen_mes:[],saldos:[],presupuesto:{limites:{diario:null,semanal:null},gastos:[]}}) : path.includes('/installment-drafts?') ? ({borradores:0,items:[],next_offset:null}) : path.includes('/installments?month=') ? ({mes:new URL('https://local'+path).searchParams.get('month'),totales:[],items:[],next_offset:null}) : ({items:(path.includes('/expenses') || path.includes('/incomes') || path.includes('/transfers') || path.includes('/savings-goals') || path.includes('/commitments')) ? [] : accounts,next_offset:null});
      },
    }}]});
    const fixture=TestBed.createComponent(Accounts);
    fixture.componentRef.setInput('space','s'); fixture.detectChanges();
    await fixture.whenStable(); fixture.detectChanges();
    await fixture.whenStable(); fixture.detectChanges();
    return {fixture, component:fixture.componentInstance};
  }
  it('abre Hoy y muestra el resumen mensual cuando no hay pendientes', async () => {
    const {fixture,component}=await setup();
    expect(component.tab()).toBe('today');
    const panel=fixture.nativeElement.querySelector('app-due-overview');
    expect(panel.textContent).toContain('No tenés vencimientos pendientes');
    expect(panel.textContent).toContain('Resumen de cuotas del mes');
    panel.querySelector('section > button').click();
    expect(component.tab()).toBe('debts');
  });
  it('muestra la distribución en Hoy y abre movimientos con los filtros de la categoría', async () => {
    const { fixture, component } = await setup(true);
    window.dispatchEvent(new CustomEvent('gastos-privacy', { detail: false }));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    const expenseReport = fixture.nativeElement.querySelector('app-today-category-report');
    const categories = expenseReport.querySelectorAll('.category-row');
    expect(categories).toHaveLength(3);
    expect(categories[0].textContent).toContain('Ocio');
    expect(categories[0].textContent).toContain('49,0%');
    categories[0].click();
    expect(component.tab()).toBe('movements');
    expect(component.movementReport()).toEqual({
      desde: '2026-11-01', hasta: '2026-11-30', categoria: 'ocio', moneda: 'ARS',
    });
  });
  it('abre el mes del aviso cuando coincide con el espacio autenticado', async () => {
    const previous = location.pathname + location.search + location.hash;
    try {
      history.replaceState(null, '', '?espacio=s&mes=2026-10&aviso=importe');
      const { fixture, component } = await setup();
      expect(component.tab()).toBe('debts');
      expect(component.commitments?.appliedMonth()).toBe('2026-10');
      expect(component.commitments?.draftMonth()).toBe('2026-10');
      fixture.destroy();
    } finally {
      history.replaceState(null, '', previous);
    }
  });
  it('no aplica un enlace dirigido a otro espacio', async () => {
    const previous = location.pathname + location.search + location.hash;
    try {
      history.replaceState(null, '', '?espacio=otro&mes=2026-10&aviso=importe');
      const { component } = await setup();
      expect(component.tab()).toBe('today');
      expect(component.installmentReminder()).toBeNull();
    } finally {
      history.replaceState(null, '', previous);
    }
  });
  it('muestra en Hoy los límites alcanzados, respeta la privacidad y abre el presupuesto', async () => {
    const { fixture, component } = await setup(true);
    window.dispatchEvent(new CustomEvent('gastos-privacy', { detail: false }));
    fixture.detectChanges();
    const panel: HTMLElement = fixture.nativeElement.querySelector('app-due-overview .budget-alerts');
    expect(panel.textContent).toContain('Alimentos');
    expect(panel.textContent).toContain('Cerca del límite · 80,0%');
    expect(panel.textContent).toContain('Límite superado · 125,0%');
    expect(panel.textContent).not.toContain('Salud');
    window.dispatchEvent(new CustomEvent('gastos-privacy', { detail: true }));
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.budget-alerts')).toBeNull();

    window.dispatchEvent(new CustomEvent('gastos-privacy', { detail: false }));
    fixture.detectChanges();
    fixture.nativeElement.querySelector('.budget-alerts button').click();
    expect(component.tab()).toBe('plan');
  });
  it('muestra el exceso bajo la navegación y permite cerrar el aviso', async () => {
    const { fixture } = await setup(false, true);
    window.dispatchEvent(new CustomEvent('gastos-privacy', { detail: false }));
    fixture.detectChanges();
    const notices: HTMLElement = fixture.nativeElement.querySelector('app-budget-alerts');
    expect(notices.textContent).toContain('Superaste el límite por ARS 25,00');
    window.dispatchEvent(new CustomEvent('gastos-privacy', { detail: true }));
    fixture.detectChanges();
    expect(notices.querySelector('section')).toBeNull();
    window.dispatchEvent(new CustomEvent('gastos-privacy', { detail: false }));
    fixture.detectChanges();
    notices.querySelector('button')!.click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(notices.querySelector('section')).toBeNull();
  });
  it('enfoca el importe de la carga rápida desde Hoy y puede volver a la sección anterior', async () => {
    const { fixture, component } = await setup();
    fixture.nativeElement.querySelector('.quick-expense-action').click();
    const amount = fixture.nativeElement.querySelector('#quick-expense-amount');
    expect(component.tab()).toBe('expenses');
    expect(document.activeElement).toBe(amount);
    expect(amount.inputMode).toBe('decimal');
    component.finishQuickExpense();
    expect(component.tab()).toBe('today');
  });
  it('conserva instancia, borrador y filtros al visitar Cuentas', async () => {
    const {fixture,component}=await setup();
    const expenses=component.expenses!;
    expenses.description='Compra pendiente'; expenses.filterText='café';
    component.tab.set('accounts'); fixture.detectChanges();
    component.tab.set('expenses'); fixture.detectChanges();
    expect(component.expenses).toBe(expenses);
    expect(expenses.description).toBe('Compra pendiente');
    expect(expenses.filterText).toBe('café');
  });
  it('abre el registro en pantallas chicas con el importe como primer campo', async () => {
    vi.stubGlobal('matchMedia', (query: string) => ({ matches: query === '(max-width: 767px)' }));
    try {
      const { fixture, component } = await setup();
      expect(component.tab()).toBe('expenses');
      const editor: HTMLDetailsElement = fixture.nativeElement.querySelector('.expense-editor');
      expect(editor.open).toBe(true);
      expect(editor.querySelector('input, select')?.id).toBe('expense-amount');
    } finally {
      vi.unstubAllGlobals();
    }
  });
  it('protege un borrador y permite cambiar de cuenta cuando se termina', async () => {
    const {fixture,component}=await setup();
    component.expenses!.description='Compra pendiente';
    component.choose('two');
    expect(component.selected()[0].id).toBe('');
    expect(component.error()).toContain('Terminá');
    component.expenses!.description=''; component.choose('two'); fixture.detectChanges();
    expect(component.selected()[0].id).toBe('two');
  });
  it('protege el ingreso pendiente al cambiar de cuenta', async () => {
    const {fixture,component}=await setup();
    component.incomes!.description='Sueldo pendiente';component.choose('two');
    expect(component.selected()[0].id).toBe('');
    component.incomes!.cancel();component.choose('two');fixture.detectChanges();
    expect(component.selected()[0].id).toBe('two');
  });
  it('conserva el borrador de ahorro al cambiar de seccion', async () => {
    const {fixture,component}=await setup();
    const transfers=fixture.debugElement.query(By.directive(Transfers)).componentInstance as Transfers;
    component.tab.set('savings');fixture.detectChanges();transfers.origin='one';transfers.destination='two';transfers.amount='100';transfers.description='Ahorro pendiente';
    const savingsPanels: HTMLElement = fixture.nativeElement.querySelector('.savings-panels');
    expect(savingsPanels.hidden).toBe(false);
    component.tab.set('accounts');
    fixture.detectChanges();
    expect(savingsPanels.hidden).toBe(true);
    component.tab.set('savings');
    fixture.detectChanges();
    expect(savingsPanels.hidden).toBe(false);
    expect(fixture.debugElement.query(By.directive(Transfers)).componentInstance).toBe(transfers);
    expect(transfers.amount).toBe('100');expect(transfers.description).toBe('Ahorro pendiente');
  });
  it('prepara el aporte sin sobrescribir una transferencia pendiente', async () => {
    const {fixture,component}=await setup();
    const transfer=component.transfers!;
    const goal={cuenta_id:'two',cuenta_nombre:'Banco',nombre:'Vacaciones',moneda:'USD',retirar:false};
    component.fundGoal(goal);expect(transfer.destination).toBe('two');expect(transfer.currency).toBe('USD');
    transfer.amount='10';component.fundGoal({...goal,retirar:true});
    expect(transfer.destination).toBe('two');expect(transfer.amount).toBe('10');expect(transfer.error()).toContain('pendiente');
    fixture.destroy();
  });
  it('conserva el borrador de deuda al cambiar de seccion', async () => {
    const {fixture,component}=await setup();
    const debt=fixture.debugElement.query(By.directive(Commitments)).componentInstance as Commitments;
    component.tab.set('debts');fixture.detectChanges();debt.name='Casa';debt.amount='250';debt.count=10;
    component.tab.set('accounts');fixture.detectChanges();component.tab.set('debts');fixture.detectChanges();
    expect(fixture.debugElement.query(By.directive(Commitments)).componentInstance).toBe(debt);
    expect(debt.name).toBe('Casa');expect(debt.amount).toBe('250');
  });
  it('abre el formulario cuando se elige editar un gasto', async () => {
    const {fixture,component}=await setup();
    component.expenses!.editorOpen = false;
    fixture.detectChanges();
    component.expenses!.edit({id:'expense',espacio_id:'s',cuenta_id:'one',fecha:'2026-11-01',descripcion:'Verduras',moneda:'ARS',importe:'5000.00'});
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.expense-editor').open).toBe(true);
    expect(component.expenses!.date).toBe('2026-11-01');
  });
});
