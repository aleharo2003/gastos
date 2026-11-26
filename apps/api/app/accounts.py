"""Cuentas por espacio: identidad del JWT, autorizacion y RLS."""
import re
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request, Response, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from app.auth import me
from app.db.unit_of_work import runtime_transaction

router = APIRouter()
NO_STORE = {'Cache-Control': 'no-store'}
PROFILE_FIELDS = ('tipo', 'moneda', 'saldo_inicial', 'dia_cierre', 'dia_vencimiento',
                  'fecha_vencimiento', 'tasa_anual')
ACCOUNT_COLUMNS = 'id, espacio_id, nombre, ' + ', '.join(PROFILE_FIELDS)


class AccountName(BaseModel):
    model_config = ConfigDict(extra='forbid')
    nombre: str

    @field_validator('nombre')
    @classmethod
    def valid_name(cls, value):
        value = value.strip()
        if not 1 <= len(value) <= 80 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('Usar un nombre de 1 a 80 caracteres sin controles')
        return value


class AccountInput(AccountName):
    id: UUID
    tipo: Literal['efectivo', 'banco', 'tarjeta_credito', 'billetera', 'inversion'] | None = None
    moneda: Literal['ARS', 'USD', 'EUR'] | None = None
    saldo_inicial: Decimal | None = None
    dia_cierre: int | None = Field(default=None, strict=True, ge=1, le=31)
    dia_vencimiento: int | None = Field(default=None, strict=True, ge=1, le=31)
    fecha_vencimiento: date | None = None
    tasa_anual: Decimal | None = None

    @field_validator('saldo_inicial', 'tasa_anual', mode='before')
    @classmethod
    def exact_decimal(cls, value, info):
        if value is None:
            return value
        pattern = (r'-?(?:0|[1-9][0-9]{0,11})\.[0-9]{2}' if info.field_name == 'saldo_inicial'
                   else r'(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{1,4})?')
        if not isinstance(value, str) or not re.fullmatch(pattern, value):
            raise ValueError('Formato decimal inválido')
        return Decimal(value)

    @field_validator('fecha_vencimiento', mode='before')
    @classmethod
    def exact_date(cls, value):
        if value is not None and (not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value)):
            raise ValueError('Ingresá una fecha válida')
        return value

    @model_validator(mode='after')
    def complete_profile(self):
        if all(getattr(self, key) is None for key in PROFILE_FIELDS):
            return self
        if self.tipo is None or self.moneda is None or self.saldo_inicial is None:
            raise ValueError('Indicá tipo, moneda y saldo inicial')
        card = (self.dia_cierre, self.dia_vencimiento)
        investment = (self.fecha_vencimiento, self.tasa_anual)
        for pair, required in ((card, self.tipo == 'tarjeta_credito'), (investment, self.tipo == 'inversion')):
            if any((value is not None) != required for value in pair):
                raise ValueError('Completá los datos correspondientes al tipo de cuenta')
        if self.tipo == 'inversion' and self.saldo_inicial <= 0:
            raise ValueError('El capital inicial debe ser mayor a cero')
        return self

    @field_validator('id')
    @classmethod
    def nonzero(cls, value):
        if value.int == 0:
            raise ValueError('Identificador invalido')
        return value


class AccountRename(AccountName):
    nombre_anterior: str

    @field_validator('nombre_anterior')
    @classmethod
    def previous_name(cls, value):
        if not 1 <= len(value) <= 80 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('Nombre anterior invalido')
        return value


class AccountState(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    activa: bool


def require_member(session, user, space, write=False):
    role = session.execute(text('SELECT rol FROM public.miembros_espacio WHERE usuario_id=:u AND espacio_id=:s'),
                           {'u':user, 's':space}).scalar_one_or_none()
    if role not in (('owner', 'editor') if write else ('owner', 'editor', 'lector')):
        raise HTTPException(403, 'Sin permiso para esta operacion', headers=NO_STORE)


def public_account(row):
    result = dict(row)
    if result['tipo'] is None:
        for key in PROFILE_FIELDS:
            result.pop(key)
    else:
        for key, places in (('saldo_inicial', 2), ('tasa_anual', 4)):
            if result[key] is not None:
                result[key] = format(result[key], f'.{places}f')
    return result


def list_accounts(session, user, space, offset=0, inactive=False):
    require_member(session, user, space)
    rows = session.execute(text(f'SELECT {ACCOUNT_COLUMNS} FROM public.cuentas WHERE espacio_id=:s AND activa=:activa ORDER BY id LIMIT 101 OFFSET :offset'),
                           {'s':space, 'offset':offset, 'activa':not inactive}).mappings().all()
    return {'items': [public_account(row) for row in rows[:100]], 'next_offset': offset + 100 if len(rows) > 100 else None}


def create_account(session, user, space, body):
    require_member(session, user, space, write=True)
    fields = body.model_dump()
    values = ', '.join(':' + key for key in ('id', 'espacio_id', 'nombre', *PROFILE_FIELDS))
    session.execute(text(f'INSERT INTO public.cuentas({ACCOUNT_COLUMNS}) VALUES ({values}) ON CONFLICT (id) DO NOTHING'),
                    {**fields, 'espacio_id': space})
    row = session.execute(text(f'SELECT {ACCOUNT_COLUMNS} FROM public.cuentas WHERE id=:id AND espacio_id=:s'),
                          {'id':body.id, 's':space}).mappings().one_or_none()
    if row is None or any(row[key] != fields[key] for key in ('nombre', *PROFILE_FIELDS)):
        raise HTTPException(409, 'El identificador ya fue usado para otra cuenta', headers=NO_STORE)
    return public_account(row)


def rename_account(session, user, space, account, body):
    require_member(session, user, space, write=True)
    params = {'id': account, 's': space, 'n': body.nombre}
    row = session.execute(text(f"""
        SELECT {ACCOUNT_COLUMNS} FROM public.cuentas
        WHERE id=:id AND espacio_id=:s FOR NO KEY UPDATE
    """), params).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, 'Cuenta no encontrada', headers=NO_STORE)
    if row['nombre'] == body.nombre:
        return public_account(row)
    if row['nombre'] != body.nombre_anterior:
        raise HTTPException(409, 'Otra sesion cambio el nombre de la cuenta', headers=NO_STORE)
    updated = session.execute(text(f"""
        UPDATE public.cuentas SET nombre=:n WHERE id=:id AND espacio_id=:s
        RETURNING {ACCOUNT_COLUMNS}
    """), params).mappings().one()
    return public_account(updated)


def get_account_state(session, user, space, account):
    require_member(session, user, space)
    row = session.execute(text(f"""
        SELECT {ACCOUNT_COLUMNS}, activa FROM public.cuentas
        WHERE id=:id AND espacio_id=:s
    """), {'id': account, 's': space}).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, 'Cuenta no encontrada', headers=NO_STORE)
    return public_account(row)


def set_account_state(session, user, space, account, active):
    require_member(session, user, space, write=True)
    row = session.execute(text(f"""
        UPDATE public.cuentas SET activa=:active WHERE id=:id AND espacio_id=:s
        RETURNING {ACCOUNT_COLUMNS}, activa
    """), {'id': account, 's': space, 'active': active}).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, 'Cuenta no encontrada', headers=NO_STORE)
    return public_account(row)


def execute(request, response, space, operation, *, repeatable_read=False):
    identity = me(request, response)
    engine = getattr(request.app.state, 'runtime_engine', None)
    if engine is None:
        raise HTTPException(503, 'Base no disponible', headers=NO_STORE)
    try:
        with runtime_transaction(engine, usuario_id=identity['usuario_id'], espacio_id=space,
                                 repeatable_read=repeatable_read) as session:
            return operation(session, identity['usuario_id'])
    except SQLAlchemyError as error:
        if isinstance(error, DBAPIError) and getattr(getattr(error.orig, 'diag', None), 'constraint_name', None) == 'cuenta_activa_para_movimientos':
            raise HTTPException(409, 'La cuenta está inactiva', headers=NO_STORE) from None
        raise HTTPException(503, 'No se pudo completar la operacion', headers=NO_STORE) from None


@router.get('/spaces/{space}/accounts')
def get_accounts(space: UUID, request: Request, response: Response, offset: int = Query(default=0, ge=0, le=100000), inactivas: bool = False):
    return execute(request, response, space, lambda session, user: list_accounts(session, user, space, offset, inactivas))


@router.post('/spaces/{space}/accounts')
def post_account(space: UUID, body: AccountInput, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: create_account(session, user, space, body))

@router.patch('/spaces/{space}/accounts/{account}')
def patch_account(space: UUID, account: UUID, body: AccountRename, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: rename_account(session, user, space, account, body))

@router.get('/spaces/{space}/accounts/{account}')
def read_account(space: UUID, account: UUID, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: get_account_state(session, user, space, account))


@router.patch('/spaces/{space}/accounts/{account}/status')
def patch_account_state(space: UUID, account: UUID, body: AccountState, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: set_account_state(session, user, space, account, body.activa))
