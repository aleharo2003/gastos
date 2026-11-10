import { Component, DestroyRef, inject, Input, OnInit, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthSession } from './auth-session';

type Receipt={id:string;nombre:string;mime:string;bytes:number};
const MAX=5*1024*1024;
@Component({selector:'app-receipts',templateUrl:'./receipts.html',styleUrl:'./receipts.css'})
export class Receipts implements OnInit {
  @Input({required:true}) path='';
  readonly items=signal<Receipt[]>([]);
  readonly busy=signal(false);
  readonly error=signal('');
  readonly notice=signal('');
  readonly preview=signal('');
  readonly selected=signal<File|null>(null);
  private pendingId='';
  private alive=true;
  private readonly auth=inject(AuthSession);
  constructor(){inject(DestroyRef).onDestroy(()=>{this.alive=false;this.closePreview();});}
  ngOnInit(){void this.load();}
  closePreview(){if(this.preview())URL.revokeObjectURL(this.preview());this.preview.set('');}
  async load(){
    if(this.busy())return;this.busy.set(true);this.error.set('');
    try{const page=await this.auth.accountRequest<{items:Receipt[]}>('GET',this.path);if(this.alive)this.items.set(page.items);}
    catch{if(this.alive)this.error.set('No pudimos cargar los comprobantes. Podés actualizar la lista.');}
    finally{if(this.alive)this.busy.set(false);}
  }
  choose(event:Event){
    const input=event.target as HTMLInputElement,file=input.files?.[0];input.value='';
    if(!file||this.busy())return;
    this.selected.set(null);this.pendingId='';
    this.error.set('');this.notice.set('');
    if(!['image/jpeg','image/png','application/pdf'].includes(file.type)||file.size===0||file.size>MAX){
      this.error.set('Elegí un JPG, PNG o PDF de hasta 5 MB. Si la foto es HEIC, exportala como JPG.');return;
    }
    if([...file.name].length>160||/[\x00-\x1f\x7f/\\]/.test(file.name)){
      this.error.set('Usá un nombre de archivo de hasta 160 caracteres, sin barras.');return;
    }
    this.selected.set(file);this.pendingId=crypto.randomUUID();
  }
  async upload(){
    const file=this.selected();if(!file||this.busy())return;
    this.busy.set(true);this.error.set('');this.notice.set('');
    try{
      const row=await this.auth.uploadReceipt<Receipt>(`${this.path}/${this.pendingId}`,file);
      if(!this.alive)return;
      this.items.update(items=>[...items.filter(r=>r.id!==row.id),row]);
      this.selected.set(null);this.pendingId='';this.notice.set('Comprobante guardado.');
    }catch(e){if(this.alive){
      const status=e instanceof HttpErrorResponse?e.status:0;
      this.error.set(status===403?'No tenés permiso para adjuntar en este espacio.':status===409?'Se alcanzó el límite o el identificador ya está usado. Actualizá la lista.':status===415||status===422?'El archivo no tiene un formato admitido. Elegí otro JPG, PNG o PDF.':status===413?'El archivo supera el máximo de 5 MB.':'No pudimos confirmar la subida. El gasto sigue guardado. Tocá Subir para reintentar el mismo archivo.');
    }}finally{if(this.alive)this.busy.set(false);}
  }
  async file(row:Receipt,view=false){
    if(this.busy())return;this.busy.set(true);this.error.set('');
    try{
      const blob=await this.auth.downloadReceipt(`${this.path}/${row.id}/file`);
      if(!this.alive)return;
      if(blob.size>MAX||blob.type.split(';')[0]!==row.mime)throw new Error('Archivo inesperado');
      if(view&&row.mime.startsWith('image/')){this.closePreview();this.preview.set(URL.createObjectURL(blob));}
      else{
        const url=URL.createObjectURL(blob),link=document.createElement('a');
        link.href=url;link.download=`comprobante-${row.id}.${row.mime==='application/pdf'?'pdf':row.mime==='image/png'?'png':'jpg'}`;
        document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
      }
    }catch{if(this.alive)this.error.set('No pudimos recuperar el archivo. Volvé a intentar.');}
    finally{if(this.alive)this.busy.set(false);}
  }
}
