import { TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { vi } from 'vitest';
import { Planning } from './planning';
import { AuthSession } from './auth-session';
describe('Plan compartido y límites globales',()=>{
  afterEach(()=>{localStorage.clear();vi.restoreAllMocks();});
  async function setup(){
    const value={version:1,datos:{limites:{diario:null,semanal:{moneda:'USD',importe:'200.00'}},conceptos:[]}};
    const summary={fecha:'2026-11-12',mes:'2026-11',semana_desde:'2026-11-09',semana_hasta:'2026-11-15',totales:[{moneda:'USD',dia:'10.00',semana:'250.00',mes:'500.00'}]};
    const request=vi.fn().mockImplementation(async(method,path,body)=>path.includes('expense-summary')?summary:path.includes('expense-category-summary')?{desde:'2026-11-01',hasta:'2026-11-30',items:[]}:method==='POST'?{version:2,datos:body.datos}:structuredClone(value));
    TestBed.configureTestingModule({imports:[Planning],providers:[{provide:AuthSession,useValue:{accountRequest:request}}]});
    const f=TestBed.createComponent(Planning);f.componentRef.setInput('space','s');f.componentRef.setInput('compact',false);f.detectChanges();await f.whenStable();f.detectChanges();
    return {f,c:f.componentInstance,request,value};
  }
  it('usa todas las cuentas y alerta sin bloquear nuevas cargas',async()=>{
    const {f,c,request}=await setup();
    expect(request).toHaveBeenCalledWith('GET','/api/spaces/s/expense-summary');
    expect(c.limit('semanal')!.spent).toBe(25000n);
    expect(f.nativeElement.textContent).toContain('Superaste el límite por');
    expect(f.nativeElement.textContent).toContain('125,0%');
    expect(f.nativeElement.querySelector('.limit-balance strong')?.textContent).toContain('USD 50,00');
  });
  it('guarda solo configuración versionada, normaliza el importe y conserva borrador ante conflicto',async()=>{
    const {c,request}=await setup();c.weekly='220,50';c.dirty=true;
    await c.save();expect(request.mock.calls.filter(call=>call[0]==='POST')[0]).toEqual(['POST','/api/spaces/s/spending-plan',{version:1,datos:{limites:{diario:null,semanal:{moneda:'USD',importe:'220.50'}},conceptos:[]}}]);
    c.weekly='230';c.dirty=true;request.mockRejectedValue(new HttpErrorResponse({status:409}));await c.save();
    expect(c.weekly).toBe('230');expect(c.dirty).toBe(true);expect(c.error()).toContain('Otra sesión');
  });
  it('guarda y quita el límite mensual global y calcula el consumo del mes', async () => {
    const { c, request } = await setup();
    c.monthly = '600,0';
    c.monthlyCurrency = 'USD';
    await c.save();
    const posts = () => request.mock.calls.filter(([method]) => method === 'POST');
    expect(posts()[0][2].datos.limites.mensual).toEqual({ moneda: 'USD', importe: '600.00' });
    expect(c.limit('mensual')).toMatchObject({ spent: 50000n, difference: 10000n });

    c.monthly = '';
    await c.save();
    expect(posts()[1][2].datos.limites.mensual).toBeNull();
  });
  it('el ojo oculta montos y gráficos del presupuesto',async()=>{
    const {f}=await setup();window.dispatchEvent(new CustomEvent('gastos-privacy',{detail:true}));f.detectChanges();
    expect(f.nativeElement.textContent).not.toContain('125,0%');expect(f.nativeElement.textContent).not.toContain('200,00');expect(f.nativeElement.querySelector('form')).toBeNull();
  });
  it('conserva el borrador al cerrar y abrir el editor', async () => {
    const { f, c } = await setup();
    const editor: HTMLDetailsElement = f.nativeElement.querySelector('.budget-editor');
    const input = editor.querySelector<HTMLInputElement>('#weekly-limit')!;
    expect(editor.open).toBe(false);
    editor.open = true;
    input.value = '240';
    input.dispatchEvent(new Event('input'));
    editor.open = false;
    f.detectChanges();
    editor.open = true;
    f.detectChanges();
    expect(c.weekly).toBe('240');
    expect(c.dirty).toBe(true);
    expect(input.value).toBe('240');
  });
  it('guarda, calcula y quita un límite mensual por categoría', async () => {
    const { f, c, request } = await setup();
    const report = { desde: '2026-11-01', hasta: '2026-11-30', items: [
      { categoria: 'alimentos', moneda: 'ARS', total: '75.00' },
      { categoria: 'alimentos', moneda: 'USD', total: '0.10' },
      { categoria: 'ocio', moneda: 'ARS', total: '500.00' },
    ] };
    request.mockImplementation(async (method, url, payload) =>
      method === 'POST' ? { version: 2, datos: payload.datos } : report);
    c.categoryToAdd = 'alimentos';
    c.addCategoryLimit();
    c.draft.limites_categoria![0].importe = '100,0';
    await c.save();
    await f.whenStable();

    const writes = () => request.mock.calls.filter(call => call[0] === 'POST');
    expect(writes()[0][2].datos.limites_categoria).toEqual([
      { categoria: 'alimentos', moneda: 'ARS', importe: '100.00' },
    ]);
    expect(c.categoryUsage()[0].spent).toBeNull();
    c.rate.set('100');
    f.detectChanges();
    expect(c.categoryUsage()[0].spent).toBe(8500n);
    expect(f.nativeElement.querySelector('.category-limits').textContent).toContain('15,00');
    expect(f.nativeElement.querySelector('.category-limits').textContent).toContain('Estás cerca del límite');

    c.removeCategoryLimit('alimentos');
    await c.save();
    expect(writes()[1][2].datos.limites_categoria).toEqual([]);
    expect(c.categoryUsage()).toEqual([]);
  });
  it('incluye gastos sin límite en el total y muestra el presupuesto sin consumo', async () => {
    const { f, c, value } = await setup();
    c.saved.set({
      ...value,
      datos: { ...c.saved()!.datos, limites_categoria: [{ categoria: 'alimentos', moneda: 'ARS', importe: '100.00' }] },
    });
    c.categorySpending.set({ desde: '2026-11-01', hasta: '2026-11-30', items: [
      { categoria: 'ocio', moneda: 'ARS', total: '42.00' },
      { categoria: null, moneda: 'ARS', total: '8.00' },
      { categoria: 'ocio', moneda: 'USD', total: '2.00' },
    ] });
    expect(c.categoryUsage()[0]).toMatchObject({ spent: 0n, difference: 10000n });
    expect(c.categoryComparison()?.totals).toEqual([['ARS', 5000n], ['USD', 200n]]);
    f.detectChanges();
    const comparison = f.nativeElement.querySelector('.category-limits').textContent;
    expect(comparison).toContain('Gastos sin presupuesto');
    expect(comparison).toContain('Sin categoría');
    expect(comparison).toContain('ARS 50,00');
    expect(comparison).toContain('ARS 100,00');
  });

  it('no descarta cambios al recargar sin confirmación',async()=>{
    const {c,request}=await setup();c.dirty=true;c.weekly='321';const calls=request.mock.calls.length;
    vi.spyOn(window,'confirm').mockReturnValue(false);await c.load();expect(request.mock.calls.length).toBe(calls);expect(c.weekly).toBe('321');
  });
});
