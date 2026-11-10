"""Comprobantes de gastos, autorizados por espacio; nunca URLs públicas."""
import hashlib
from urllib.parse import unquote
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool
from sqlalchemy import text
from app.accounts import execute, NO_STORE
from app.auth import me
from app.expenses import require_account
from app.receipt_storage import ReceiptStorage, MAX_BYTES

router = APIRouter()
PREFIX = '/spaces/{space}/accounts/{account}/expenses/{expense}/receipts'


def authorize(session, user, space, account, expense, write=False):
    require_account(session,user,space,account,write)
    found=session.execute(text('SELECT id FROM public.gastos WHERE id=:e AND espacio_id=:s AND cuenta_id=:a'),
                          {'e':expense,'s':space,'a':account}).scalar_one_or_none()
    if found is None:
        raise HTTPException(404,'Gasto no disponible',headers=NO_STORE)


def file_type(data):
    if data.startswith(b'\xff\xd8\xff') and data.endswith(b'\xff\xd9'): return 'image/jpeg','jpg'
    if data.startswith(b'\x89PNG\r\n\x1a\n') and data.endswith(b'IEND\xaeB`\x82'): return 'image/png','png'
    if data.startswith(b'%PDF-') and b'%%EOF' in data[-1024:]: return 'application/pdf','pdf'
    raise HTTPException(415,'Usa un archivo JPG, PNG o PDF valido',headers=NO_STORE)


def public(row):
    return {key:str(row[key]) if key=='id' else row[key] for key in ('id','nombre','mime','bytes')}


def list_receipts(session,user,space,account,expense):
    authorize(session,user,space,account,expense)
    rows=session.execute(text('SELECT id,nombre,mime,bytes FROM public.comprobantes WHERE espacio_id=:s AND gasto_id=:e ORDER BY id LIMIT 5'),{'s':space,'e':expense}).mappings().all()
    return {'items':[public(r) for r in rows]}


def save_receipt(session,user,space,account,expense,receipt,name,data,storage=None):
    authorize(session,user,space,account,expense,True)
    if receipt.int==0 or not 1<=len(data)<=MAX_BYTES:
        raise HTTPException(413,'Archivo vacio o mayor a 5 MB',headers=NO_STORE)
    if not 1<=len(name)<=160 or any(ord(c)<32 or ord(c)==127 or c in '/\\' for c in name):
        raise HTTPException(422,'Nombre de archivo invalido',headers=NO_STORE)
    mime,extension=file_type(data);digest=hashlib.sha256(data).hexdigest()
    # Serializa altas por espacio para aplicar límites también con subidas concurrentes.
    session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:s, 0))'),{'s':str(space)})
    params={'id':receipt,'s':space,'e':expense,'n':name,'m':mime,'b':len(data),'h':digest}
    old=session.execute(text('SELECT * FROM public.comprobantes WHERE id=:id'),params).mappings().one_or_none()
    if old is not None:
        if str(old['gasto_id'])!=str(expense) or old['sha256']!=digest or old['nombre']!=name:
            raise HTTPException(409,'Identificador de comprobante ya utilizado',headers=NO_STORE)
        return public(old)
    count=session.execute(text('SELECT count(*) FROM public.comprobantes WHERE espacio_id=:s AND gasto_id=:e'),params).scalar_one()
    size=session.execute(text('SELECT coalesce(sum(bytes),0) FROM public.comprobantes WHERE espacio_id=:s'),params).scalar_one()
    if count>=5 or size+len(data)>200*1024*1024:
        raise HTTPException(409,'Limite: cinco comprobantes por gasto o 200 MB por espacio',headers=NO_STORE)
    params['p']=f'{space}/{expense}/{receipt}/{digest}.{extension}'
    inserted=session.execute(text('''INSERT INTO public.comprobantes(id,espacio_id,gasto_id,nombre,mime,bytes,sha256,ruta)
        VALUES (:id,:s,:e,:n,:m,:b,:h,:p) ON CONFLICT (id) DO NOTHING RETURNING *'''),params).mappings().one_or_none()
    if inserted is None:
        raise HTTPException(409,'Identificador no disponible',headers=NO_STORE)
    (storage or ReceiptStorage()).put(params['p'],data,mime)
    return public(inserted)


def download_receipt(session,user,space,account,expense,receipt,storage=None):
    authorize(session,user,space,account,expense)
    row=session.execute(text('SELECT * FROM public.comprobantes WHERE id=:id AND espacio_id=:s AND gasto_id=:e'),
                        {'id':receipt,'s':space,'e':expense}).mappings().one_or_none()
    if row is None: raise HTTPException(404,'Comprobante no disponible',headers=NO_STORE)
    data=(storage or ReceiptStorage()).get(row['ruta'])
    if len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256']:
        raise HTTPException(503,'No se pudo verificar el archivo',headers=NO_STORE)
    ext={'image/jpeg':'jpg','image/png':'png','application/pdf':'pdf'}[row['mime']]
    return Response(data,media_type=row['mime'],headers={**NO_STORE,'X-Content-Type-Options':'nosniff',
        'Content-Disposition':f'attachment; filename="comprobante-{receipt}.{ext}"'})


@router.get(PREFIX)
def listing(space:UUID,account:UUID,expense:UUID,request:Request,response:Response):
    return execute(request,response,space,lambda s,u:list_receipts(s,u,space,account,expense))


@router.post(PREFIX+'/{receipt}')
async def upload(space:UUID,account:UUID,expense:UUID,receipt:UUID,request:Request,response:Response):
    me(request,response)
    # Rechazar falta de membresía antes de recibir y almacenar el cuerpo completo.
    await run_in_threadpool(execute,request,response,space,lambda s,u:authorize(s,u,space,account,expense,True))
    if request.headers.get('content-type')!='application/octet-stream':
        raise HTTPException(415,'Contenido no admitido',headers=NO_STORE)
    name=unquote(request.headers.get('x-receipt-name',''))
    data=bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data)>MAX_BYTES: raise HTTPException(413,'Maximo 5 MB',headers=NO_STORE)
    return await run_in_threadpool(execute,request,response,space,
        lambda s,u:save_receipt(s,u,space,account,expense,receipt,name,bytes(data)))


@router.get(PREFIX+'/{receipt}/file')
def download(space:UUID,account:UUID,expense:UUID,receipt:UUID,request:Request,response:Response):
    return execute(request,response,space,lambda s,u:download_receipt(s,u,space,account,expense,receipt))
