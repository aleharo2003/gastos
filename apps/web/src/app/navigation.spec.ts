import { By } from '@angular/platform-browser';
import { Transfers } from './transfers';
import { TestBed } from '@angular/core/testing';
import { Accounts } from './accounts';
import { AuthSession } from './auth-session';

describe('Navegación del espacio', () => {
  async function setup() {
    const accounts = [{id:'one',espacio_id:'s',nombre:'Efectivo'}, {id:'two',espacio_id:'s',nombre:'Banco'}];
    TestBed.configureTestingModule({imports:[Accounts],providers:[{provide:AuthSession,useValue:{
      accountRequest: async (_method:string,path:string) => ({items:(path.includes('/expenses') || path.includes('/incomes') || path.includes('/transfers')) ? [] : accounts,next_offset:null}),
    }}]});
    const fixture=TestBed.createComponent(Accounts);
    fixture.componentRef.setInput('space','s'); fixture.detectChanges();
    await fixture.whenStable(); fixture.detectChanges();
    await fixture.whenStable(); fixture.detectChanges();
    return {fixture, component:fixture.componentInstance};
  }
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
    component.tab.set('accounts');fixture.detectChanges();component.tab.set('savings');fixture.detectChanges();
    expect(fixture.debugElement.query(By.directive(Transfers)).componentInstance).toBe(transfers);
    expect(transfers.amount).toBe('100');expect(transfers.description).toBe('Ahorro pendiente');
  });
  it('abre el formulario cuando se elige editar un gasto', async () => {
    const {fixture,component}=await setup();
    component.expenses!.edit({id:'expense',espacio_id:'s',cuenta_id:'one',fecha:'2026-11-01',descripcion:'Verduras',moneda:'ARS',importe:'5000.00'});
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.expense-editor').open).toBe(true);
    expect(component.expenses!.date).toBe('2026-11-01');
  });
});
