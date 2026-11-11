import { TestBed } from '@angular/core/testing';
import { Accounts } from './accounts';
import { AuthSession } from './auth-session';

describe('Navegación del espacio', () => {
  async function setup() {
    const accounts = [{id:'one',espacio_id:'s',nombre:'Efectivo'}, {id:'two',espacio_id:'s',nombre:'Banco'}];
    TestBed.configureTestingModule({imports:[Accounts],providers:[{provide:AuthSession,useValue:{
      accountRequest: async (_method:string,path:string) => ({items:path.includes('/expenses') ? [] : accounts,next_offset:null}),
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
    expect(component.selected()[0].id).toBe('one');
    expect(component.error()).toContain('Terminá');
    component.expenses!.description=''; component.choose('two'); fixture.detectChanges();
    expect(component.selected()[0].id).toBe('two');
  });
  it('abre el formulario cuando se elige editar un gasto', async () => {
    const {fixture,component}=await setup();
    component.expenses!.edit({id:'expense',espacio_id:'s',cuenta_id:'one',fecha:'2026-11-01',descripcion:'Verduras',moneda:'ARS',importe:'5000.00'});
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.expense-editor').open).toBe(true);
    expect(component.expenses!.date).toBe('2026-11-01');
  });
});
