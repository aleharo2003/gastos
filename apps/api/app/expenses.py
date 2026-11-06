"""Gastos con importes decimales, moneda explicita y pertenencia al espacio."""
from datetime import date
from decimal import Decimal
import re
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request, Response, Query
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import text
from app.accounts import execute, require_member, NO_STORE

router = APIRouter()
AMOUNT = re.compile(r'(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?')


class ExpenseInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    fecha: date
    descripcion: str
    moneda: Literal['ARS','USD','EUR']
    importe: Decimal

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


def require_account(session, user, space, account, write=False):
    require_member(session, user, space, write)
    found = session.execute(text('SELECT id FROM public.cuentas WHERE espacio_id=:s AND id=:a'),
                            {'s':space,'a':account}).scalar_one_or_none()
    if found is None:
        raise HTTPException(404, 'Cuenta no disponible', headers=NO_STORE)


def public_expense(row):
    return {'id':str(row['id']), 'espacio_id':str(row['espacio_id']), 'cuenta_id':str(row['cuenta_id']),
            'fecha':row['fecha'].isoformat(), 'descripcion':row['descripcion'], 'moneda':row['moneda'],
            'importe':format(row['importe'], '.2f')}


def list_expenses(session, user, space, account, offset=0):
    require_account(session, user, space, account)
    rows = session.execute(text('''SELECT * FROM public.gastos WHERE espacio_id=:s AND cuenta_id=:a
                                   ORDER BY fecha DESC, id DESC LIMIT 101 OFFSET :offset'''),
                           {'s':space,'a':account,'offset':offset}).mappings().all()
    return {'items':[public_expense(row) for row in rows[:100]],
            'next_offset':offset + 100 if len(rows) > 100 else None}


def create_expense(session, user, space, account, body):
    require_account(session, user, space, account, write=True)
    params = {'id':body.id,'s':space,'a':account,'u':user,'f':body.fecha,
              'd':body.descripcion,'m':body.moneda,'i':body.importe}
    session.execute(text('''INSERT INTO public.gastos(id,espacio_id,cuenta_id,usuario_id,fecha,descripcion,moneda,importe)
                            VALUES (:id,:s,:a,:u,:f,:d,:m,:i) ON CONFLICT (id) DO NOTHING'''),params)
    row = session.execute(text('SELECT * FROM public.gastos WHERE id=:id AND espacio_id=:s AND cuenta_id=:a'),
                          params).mappings().one_or_none()
    if (row is None or str(row['usuario_id']) != str(user) or row['fecha'] != body.fecha or
        row['descripcion'] != body.descripcion or row['moneda'] != body.moneda or row['importe'] != body.importe):
        raise HTTPException(409, 'Identificador usado para otro gasto', headers=NO_STORE)
    return public_expense(row)


@router.get('/spaces/{space}/accounts/{account}/expenses')
def get_expenses(space: UUID, account: UUID, request: Request, response: Response,
                 offset: int = Query(default=0, ge=0, le=100000)):
    return execute(request,response,space,lambda session,user: list_expenses(session,user,space,account,offset))


@router.post('/spaces/{space}/accounts/{account}/expenses')
def post_expense(space: UUID, account: UUID, body: ExpenseInput, request: Request, response: Response):
    return execute(request,response,space,lambda session,user: create_expense(session,user,space,account,body))
