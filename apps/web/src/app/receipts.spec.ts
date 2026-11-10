import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { Receipts } from './receipts';
import { AuthSession } from './auth-session';
describe('Comprobantes',()=>{
  async function setup(){
    const auth={accountRequest:vi.fn().mockResolvedValue({items:[]}),uploadReceipt:vi.fn(),downloadReceipt:vi.fn()};
    TestBed.configureTestingModule({imports:[Receipts],providers:[{provide:AuthSession,useValue:auth}]});
    const fixture=TestBed.createComponent(Receipts);fixture.componentRef.setInput('path','/api/test/receipts');fixture.detectChanges();await fixture.whenStable();
    return {fixture,component:fixture.componentInstance,auth};
  }
  function choose(c:Receipts,file:File){c.choose({target:{files:[file],value:'x'}} as unknown as Event);}
  it('conserva archivo e ID ante error y permite reintentar sin duplicar',async()=>{
    const {component:c,auth}=await setup();const file=new File(['%PDF-1.7\n%%EOF'],'ticket.pdf',{type:'application/pdf'});choose(c,file);
    auth.uploadReceipt.mockRejectedValue(new Error());await c.upload();const path=auth.uploadReceipt.mock.calls[0][0];
    expect(c.selected()).toBe(file);expect(c.error()).toContain('gasto sigue guardado');
    auth.uploadReceipt.mockResolvedValue({id:'one',nombre:'ticket.pdf',mime:'application/pdf',bytes:file.size});await c.upload();
    expect(auth.uploadReceipt.mock.calls[1][0]).toBe(path);expect(c.selected()).toBeNull();expect(c.items()).toHaveLength(1);
  });
  it('no sube HEIC ni archivos demasiado grandes',async()=>{
    const {component:c,auth}=await setup();choose(c,new File(['x'],'foto.heic',{type:'image/heic'}));await c.upload();expect(auth.uploadReceipt).not.toHaveBeenCalled();
    choose(c,new File([new Uint8Array(5*1024*1024+1)],'foto.jpg',{type:'image/jpeg'}));expect(c.selected()).toBeNull();
  });
  it('no muestra resultados si el usuario salio de la pantalla',async()=>{
    const {component:c,auth,fixture}=await setup();choose(c,new File(['%PDF-1.7\n%%EOF'],'ticket.pdf',{type:'application/pdf'}));
    let resolve!:(value:unknown)=>void;auth.uploadReceipt.mockImplementation(()=>new Promise(r=>resolve=r));const pending=c.upload();fixture.destroy();resolve({id:'one'});await pending;expect(c.items()).toEqual([]);
  });
});
