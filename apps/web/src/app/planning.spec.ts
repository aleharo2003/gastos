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
    const request=vi.fn().mockImplementation(async(method,path,body)=>path.includes('expense-summary')?summary:method==='POST'?{version:2,datos:body.datos}:structuredClone(value));
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
  });
  it('guarda solo configuración versionada, normaliza el importe y conserva borrador ante conflicto',async()=>{
    const {c,request}=await setup();c.weekly='220,50';c.dirty=true;
    await c.save();expect(request.mock.calls.filter(call=>call[0]==='POST')[0]).toEqual(['POST','/api/spaces/s/spending-plan',{version:1,datos:{limites:{diario:null,semanal:{moneda:'USD',importe:'220.50'}},conceptos:[]}}]);
    c.weekly='230';c.dirty=true;request.mockRejectedValue(new HttpErrorResponse({status:409}));await c.save();
    expect(c.weekly).toBe('230');expect(c.dirty).toBe(true);expect(c.error()).toContain('Otra sesión');
  });
  it('el ojo oculta montos y gráficos del presupuesto',async()=>{
    const {f}=await setup();window.dispatchEvent(new CustomEvent('gastos-privacy',{detail:true}));f.detectChanges();
    expect(f.nativeElement.textContent).not.toContain('125,0%');expect(f.nativeElement.textContent).not.toContain('200,00');expect(f.nativeElement.querySelector('form')).toBeNull();
  });
  it('no descarta cambios al recargar sin confirmación',async()=>{
    const {c,request}=await setup();c.dirty=true;c.weekly='321';const calls=request.mock.calls.length;
    vi.spyOn(window,'confirm').mockReturnValue(false);await c.load();expect(request.mock.calls.length).toBe(calls);expect(c.weekly).toBe('321');
  });
});
