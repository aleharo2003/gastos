"""Metas de ahorro: el saldo es su unica fuente de progreso."""
from datetime import date,datetime
from decimal import Decimal,ROUND_DOWN
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo
from fastapi import APIRouter,HTTPException,Request,Response,Query
from pydantic import BaseModel,ConfigDict,field_validator,StrictBool,StrictInt,Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.accounts import execute,require_member,NO_STORE
from app.expenses import require_account
from app.incomes import IncomeInput,account_balance

router=APIRouter()


class GoalFields(BaseModel):
    model_config=ConfigDict(extra='forbid')
    nombre:str
    objetivo:Decimal
    fecha_objetivo:date|None=None

    @field_validator('nombre')
    @classmethod
    def name(cls,value):
        return IncomeInput.description(value)

    @field_validator('objetivo',mode='before')
    @classmethod
    def amount(cls,value):
        return IncomeInput.amount(value)

    @field_validator('fecha_objetivo',mode='before')
    @classmethod
    def iso_date(cls,value):
        return None if value is None else IncomeInput.iso_date(value)


class GoalInput(GoalFields):
    id:UUID
    cuenta_id:UUID
    moneda:Literal['ARS','USD','EUR']

    @field_validator('id','cuenta_id')
    @classmethod
    def identifier(cls,value):
        return IncomeInput.identifier(value)


class GoalEdit(GoalFields):
    version:StrictInt=Field(ge=0,le=2147483646)
    archivada:StrictBool


def public_goal(row,day=None):
    saldo=row['saldo']
    saved=max(Decimal(0),saldo)
    target=row['objetivo']
    reached=saved>=target
    day=day or datetime.now(ZoneInfo('America/Argentina/Buenos_Aires')).date()
    return {key:str(row[key]) for key in ('id','espacio_id','cuenta_id')} | {
        'nombre':row['nombre'],'cuenta_nombre':row['cuenta_nombre'],'moneda':row['moneda'],
        'objetivo':format(target,'.2f'),'fecha_objetivo':row['fecha_objetivo'].isoformat() if row['fecha_objetivo'] else None,
        'archivada':row['archivada'],'version':row['version'],'saldo':format(saldo,'.2f'),
        'acumulado':format(saved,'.2f'),'faltante':format(max(Decimal(0),target-saved),'.2f'),
        'porcentaje':format((min(saved,target)*100/target).quantize(Decimal('0.1'),rounding=ROUND_DOWN),'.1f'),
        'alcanzada':reached,'vencida':bool(row['fecha_objetivo'] and row['fecha_objetivo']<day and not reached and not row['archivada'])}


def describe_goal(session,user,space,row):
    total=next(t for t in account_balance(session,user,space,row['cuenta_id'])['totales'] if t['moneda']==row['moneda'])
    name=session.execute(text('SELECT nombre FROM public.cuentas WHERE espacio_id=:s AND id=:a'),
                         {'s':space,'a':row['cuenta_id']}).scalar_one()
    return public_goal(dict(row)|{'saldo':Decimal(total['saldo']),'cuenta_nombre':name})


def create_goal(session,user,space,body):
    require_account(session,user,space,body.cuenta_id,write=True)
    params={'id':body.id,'s':space,'a':body.cuenta_id,'u':user,'n':body.nombre,'m':body.moneda,'o':body.objetivo,'f':body.fecha_objetivo}
    session.execute(text("""INSERT INTO public.metas_ahorro
        (id,espacio_id,cuenta_id,usuario_id,nombre,moneda,objetivo,fecha_objetivo,archivada,version)
        VALUES (:id,:s,:a,:u,:n,:m,:o,:f,false,0) ON CONFLICT DO NOTHING"""),params)
    row=session.execute(text('SELECT * FROM public.metas_ahorro WHERE espacio_id=:s AND id=:id'),params).mappings().one_or_none()
    if (row is None or str(row['usuario_id'])!=str(user) or row['archivada'] or
        any(row[k]!=getattr(body,k) for k in ('cuenta_id','nombre','moneda','objetivo','fecha_objetivo'))):
        raise HTTPException(409,'Ya existe una meta activa para esa cuenta y moneda, o el identificador fue usado',headers=NO_STORE)
    return describe_goal(session,user,space,row)


def edit_goal(session,user,space,goal_id,body):
    require_member(session,user,space,write=True)
    params={'s':space,'id':goal_id}
    row=session.execute(text('SELECT * FROM public.metas_ahorro WHERE espacio_id=:s AND id=:id FOR UPDATE'),params).mappings().one_or_none()
    if row is None:raise HTTPException(404,'Meta no disponible',headers=NO_STORE)
    fields=('nombre','objetivo','fecha_objetivo','archivada')
    if row['version']==body.version+1 and all(row[k]==getattr(body,k) for k in fields):
        return describe_goal(session,user,space,row)
    if row['version']!=body.version:
        raise HTTPException(409,'La meta cambio; actualiza antes de editar',headers=NO_STORE)
    params.update(n=body.nombre,o=body.objetivo,f=body.fecha_objetivo,a=body.archivada)
    try:
        with session.begin_nested():
            updated=session.execute(text("""UPDATE public.metas_ahorro SET nombre=:n,objetivo=:o,fecha_objetivo=:f,
                archivada=:a,version=version+1 WHERE espacio_id=:s AND id=:id RETURNING *"""),params).mappings().one()
    except IntegrityError as error:
        if getattr(error.orig,'sqlstate',None)=='23505':
            raise HTTPException(409,'Otra meta activa usa esa cuenta y moneda',headers=NO_STORE) from None
        raise
    return describe_goal(session,user,space,updated)


def list_goals(session,user,space,offset=0,include_archived=False):
    require_member(session,user,space)
    # DISTINCT evita multiplicar movimientos cuando hay metas archivadas sobre la misma cuenta.
    rows=session.execute(text("""
        WITH pagina AS (
          SELECT m.*,c.nombre AS cuenta_nombre FROM public.metas_ahorro m
          JOIN public.cuentas c ON c.espacio_id=m.espacio_id AND c.id=m.cuenta_id
          WHERE m.espacio_id=:s AND (:archived OR NOT m.archivada)
          ORDER BY m.archivada,m.id LIMIT 101 OFFSET :offset
        ), claves AS (SELECT DISTINCT cuenta_id,moneda FROM pagina),
        movimientos AS (
          SELECT i.cuenta_id,i.moneda,i.importe AS importe FROM public.ingresos i
          JOIN claves k ON k.cuenta_id=i.cuenta_id AND k.moneda=i.moneda WHERE i.espacio_id=:s AND i.anulado_en IS NULL
          UNION ALL
          SELECT g.cuenta_id,g.moneda,-g.importe FROM public.gastos g
          JOIN claves k ON k.cuenta_id=g.cuenta_id AND k.moneda=g.moneda WHERE g.espacio_id=:s AND g.anulado_en IS NULL
          UNION ALL
          SELECT t.destino_id,t.moneda,t.importe FROM public.transferencias t
          JOIN claves k ON k.cuenta_id=t.destino_id AND k.moneda=t.moneda WHERE t.espacio_id=:s AND t.anulado_en IS NULL
          UNION ALL
          SELECT t.origen_id,t.moneda,-t.importe FROM public.transferencias t
          JOIN claves k ON k.cuenta_id=t.origen_id AND k.moneda=t.moneda WHERE t.espacio_id=:s AND t.anulado_en IS NULL
        ), saldos AS (SELECT cuenta_id,moneda,SUM(importe) AS saldo FROM movimientos GROUP BY cuenta_id,moneda)
        SELECT p.*,COALESCE(s.saldo,0) AS saldo FROM pagina p LEFT JOIN saldos s
        ON s.cuenta_id=p.cuenta_id AND s.moneda=p.moneda ORDER BY p.archivada,p.id
        """),{'s':space,'archived':include_archived,'offset':offset}).mappings().all()
    return {'items':[public_goal(row) for row in rows[:100]],'next_offset':offset+100 if len(rows)>100 else None}


@router.get('/spaces/{space}/savings-goals')
def get_goals(space:UUID,request:Request,response:Response,offset:int=Query(default=0,ge=0,le=100000),archived:bool=False):
    return execute(request,response,space,lambda session,user:list_goals(session,user,space,offset,archived))


@router.post('/spaces/{space}/savings-goals')
def post_goal(space:UUID,body:GoalInput,request:Request,response:Response):
    return execute(request,response,space,lambda session,user:create_goal(session,user,space,body))


@router.patch('/spaces/{space}/savings-goals/{goal_id}')
def patch_goal(space:UUID,goal_id:UUID,body:GoalEdit,request:Request,response:Response):
    return execute(request,response,space,lambda session,user:edit_goal(session,user,space,goal_id,body))
