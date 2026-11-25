"""Ingresos registrados y saldos exactos por cuenta y moneda."""
from datetime import date
from decimal import Decimal
import re
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request, Response, Query
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import text
from app.accounts import execute, require_member, NO_STORE
from app.expenses import require_account
from app.movement_categories import lock_catalog, require_active_category

router = APIRouter()
AMOUNT = re.compile(r'(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?')

class IncomeInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    fecha: date
    descripcion: str
    moneda: Literal['ARS','USD','EUR']
    importe: Decimal
    categoria: str | None = None

    @field_validator('categoria')
    @classmethod
    def category(cls, value):
        if value is not None and not re.fullmatch(r'[a-z0-9_-]{1,36}', value):
            raise ValueError('Categoría inválida')
        return value

    @field_validator('id')
    @classmethod
    def identifier(cls, value):
        if value.int == 0: raise ValueError('Identificador invalido')
        return value

    @field_validator('fecha', mode='before')
    @classmethod
    def iso_date(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
            raise ValueError('Usar fecha ISO')
        return value

    @field_validator('descripcion')
    @classmethod
    def description(cls, value):
        value = value.strip()
        if not 1 <= len(value) <= 160 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('Descripcion de 1 a 160 caracteres sin controles')
        return value

    @field_validator('importe', mode='before')
    @classmethod
    def amount(cls, value):
        # JSON string: nunca convertir un float binario a dinero.
        if not isinstance(value, str) or not AMOUNT.fullmatch(value) or Decimal(value) <= 0:
            raise ValueError('Importe positivo, hasta 12 enteros y dos decimales, como texto')
        return Decimal(value)



def public_income(row):
    item = {'id':str(row['id']), 'espacio_id':str(row['espacio_id']), 'cuenta_id':str(row['cuenta_id']),
            'fecha':row['fecha'].isoformat(), 'descripcion':row['descripcion'],
            'moneda':row['moneda'], 'importe':format(row['importe'], '.2f')} | (
                {'cuenta_nombre': row['cuenta_nombre']} if 'cuenta_nombre' in row else {})
    if row['categoria'] is not None:
        item['categoria'] = row['categoria']
    return item


def create_income(session, user, space, account, body):
    require_account(session, user, space, account, write=True)
    params = {'id':body.id, 's':space, 'a':account, 'u':user, 'f':body.fecha,
              'd':body.descripcion, 'm':body.moneda, 'i':body.importe, 'c':body.categoria}
    if body.categoria is not None:
        lock_catalog(session, space)
        existing = session.execute(text('SELECT id FROM public.ingresos WHERE id=:id AND espacio_id=:s AND cuenta_id=:a'),
                                   params).scalar_one_or_none()
        if existing is None:
            require_active_category(session, space, 'ingreso', body.categoria)
    session.execute(text('''INSERT INTO public.ingresos(id,espacio_id,cuenta_id,usuario_id,fecha,descripcion,moneda,importe,categoria)
        VALUES (:id,:s,:a,:u,:f,:d,:m,:i,:c) ON CONFLICT (id) DO NOTHING'''), params)
    row = session.execute(text('SELECT * FROM public.ingresos WHERE id=:id AND espacio_id=:s AND cuenta_id=:a'),
                          params).mappings().one_or_none()
    if (row is None or str(row['usuario_id']) != str(user) or
        any(row[key] != getattr(body, key) for key in ('fecha','descripcion','moneda','importe','categoria'))):
        raise HTTPException(409, 'Identificador usado para otro ingreso', headers=NO_STORE)
    return public_income(row)


def list_incomes(session, user, space, account=None, offset=0):
    if account is None: require_member(session, user, space)
    else: require_account(session, user, space, account)
    clause = ' AND i.cuenta_id=:a' if account is not None else ''
    rows = session.execute(text("""
        SELECT i.*, c.nombre AS cuenta_nombre FROM public.ingresos i
        JOIN public.cuentas c ON c.espacio_id=i.espacio_id AND c.id=i.cuenta_id
        WHERE i.espacio_id=:s AND i.anulado_en IS NULL
    """ + clause + ' ORDER BY i.fecha DESC, i.id DESC LIMIT 101 OFFSET :offset'),
        {'s':space, 'a':account, 'offset':offset}).mappings().all()
    return {'items':[public_income(row) for row in rows[:100]],
            'next_offset':offset + 100 if len(rows) > 100 else None}


def account_balance(session, user, space, account=None):
    if account is None: require_member(session, user, space)
    else: require_account(session, user, space, account)
    clause = ' AND cuenta_id=:a' if account is not None else ''
    # Una instantanea incluye ambos lados de todas las transferencias.
    incoming = ' AND destino_id=:a' if account is not None else ''
    outgoing = ' AND origen_id=:a' if account is not None else ''
    rows = session.execute(text("""
        SELECT moneda, SUM(entrada) AS ingresos, SUM(salida) AS gastos,
            SUM(transferencia_entrada) AS transferencias_entrada,
            SUM(transferencia_salida) AS transferencias_salida,
            SUM(entrada)-SUM(salida)+SUM(transferencia_entrada)-SUM(transferencia_salida) AS saldo
        FROM (
          SELECT moneda, importe AS entrada, 0::numeric AS salida,
              0::numeric AS transferencia_entrada, 0::numeric AS transferencia_salida
          FROM public.ingresos WHERE espacio_id=:s AND anulado_en IS NULL""" + clause + """
          UNION ALL
          SELECT moneda, 0::numeric, importe, 0::numeric, 0::numeric
          FROM public.gastos WHERE espacio_id=:s AND anulado_en IS NULL""" + clause + """
          UNION ALL
          SELECT moneda, 0::numeric, 0::numeric, importe, 0::numeric
          FROM public.transferencias WHERE espacio_id=:s""" + incoming + """
          UNION ALL
          SELECT moneda, 0::numeric, 0::numeric, 0::numeric, importe
          FROM public.transferencias WHERE espacio_id=:s""" + outgoing + """
        ) movimientos GROUP BY moneda ORDER BY moneda"""), {'s':space,'a':account}).mappings().all()
    by_currency = {row['moneda']:row for row in rows}
    return {'totales':[{'moneda':currency, **{key:format(by_currency.get(currency, {}).get(key, Decimal(0)), '.2f')
                     for key in ('ingresos','gastos','transferencias_entrada','transferencias_salida','saldo')}}
                     for currency in ('ARS','USD','EUR')]}



@router.post('/spaces/{space}/accounts/{account}/incomes')
def post_income(space: UUID, account: UUID, body: IncomeInput, request: Request, response: Response):
    return execute(request,response,space,lambda session,user:create_income(session,user,space,account,body))


@router.get('/spaces/{space}/accounts/{account}/incomes')
def get_account_incomes(space: UUID, account: UUID, request: Request, response: Response,
                       offset: int = Query(default=0, ge=0, le=100000)):
    return execute(request,response,space,lambda session,user:list_incomes(session,user,space,account,offset))


@router.get('/spaces/{space}/incomes')
def get_incomes(space: UUID, request: Request, response: Response,
                offset: int = Query(default=0, ge=0, le=100000)):
    return execute(request,response,space,lambda session,user:list_incomes(session,user,space,None,offset))


@router.get('/spaces/{space}/account-balance')
def get_balance(space: UUID, request: Request, response: Response, account: UUID | None = None):
    return execute(request,response,space,lambda session,user:account_balance(session,user,space,account))
