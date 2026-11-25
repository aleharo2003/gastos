"""Un registro representa ambos lados de una transferencia interna."""
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request, Response, Query
from pydantic import model_validator
from sqlalchemy import text
from app.accounts import execute, require_member, NO_STORE
from app.expenses import require_account
from app.incomes import IncomeInput

router = APIRouter()


class TransferInput(IncomeInput):
    origen_id: UUID
    destino_id: UUID

    @model_validator(mode='after')
    def different_accounts(self):
        if self.origen_id.int == 0 or self.destino_id.int == 0 or self.origen_id == self.destino_id:
            raise ValueError('Elegir dos cuentas diferentes')
        return self


def public_transfer(row):
    return {key:str(row[key]) for key in ('id','espacio_id','origen_id','destino_id')} | {
        'fecha':row['fecha'].isoformat(), 'descripcion':row['descripcion'],
        'moneda':row['moneda'], 'importe':format(row['importe'], '.2f')}


def create_transfer(session, user, space, body):
    require_account(session,user,space,body.origen_id,write=True)
    require_account(session,user,space,body.destino_id,write=True)
    params={'id':body.id,'s':space,'o':body.origen_id,'t':body.destino_id,'u':user,
            'f':body.fecha,'d':body.descripcion,'m':body.moneda,'i':body.importe}
    # No se crean un gasto y un ingreso: ambos lados nacen del mismo registro.
    session.execute(text('''INSERT INTO public.transferencias
        (id,espacio_id,origen_id,destino_id,usuario_id,fecha,descripcion,moneda,importe)
        VALUES (:id,:s,:o,:t,:u,:f,:d,:m,:i) ON CONFLICT (id) DO NOTHING'''),params)
    row=session.execute(text('SELECT * FROM public.transferencias WHERE id=:id AND espacio_id=:s'),
                        params).mappings().one_or_none()
    if (row is None or str(row['usuario_id'])!=str(user) or
        any(row[key]!=getattr(body,key) for key in ('origen_id','destino_id','fecha','descripcion','moneda','importe'))):
        raise HTTPException(409,'Identificador usado para otra transferencia',headers=NO_STORE)
    return public_transfer(row)


def list_transfers(session,user,space,account=None,offset=0):
    if account is None: require_member(session,user,space)
    else: require_account(session,user,space,account)
    clause=' AND (origen_id=:a OR destino_id=:a)' if account is not None else ''
    rows=session.execute(text('SELECT * FROM public.transferencias WHERE espacio_id=:s AND anulado_en IS NULL'+clause+
        ' ORDER BY fecha DESC,id DESC LIMIT 101 OFFSET :offset'),
        {'s':space,'a':account,'offset':offset}).mappings().all()
    return {'items':[public_transfer(row) for row in rows[:100]],
            'next_offset':offset+100 if len(rows)>100 else None}


@router.post('/spaces/{space}/transfers')
def post_transfer(space:UUID,body:TransferInput,request:Request,response:Response):
    return execute(request,response,space,lambda session,user:create_transfer(session,user,space,body))


@router.get('/spaces/{space}/transfers')
def get_transfers(space:UUID,request:Request,response:Response,account:UUID|None=None,
                  offset:int=Query(default=0,ge=0,le=100000)):
    return execute(request,response,space,lambda session,user:list_transfers(session,user,space,account,offset))
