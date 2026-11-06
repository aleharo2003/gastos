"""Cuentas por espacio: identidad del JWT, autorizacion y RLS."""
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request, Response, Query
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.auth import me
from app.db.unit_of_work import runtime_transaction

router = APIRouter()
NO_STORE = {'Cache-Control': 'no-store'}


class AccountInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    nombre: str

    @field_validator('id')
    @classmethod
    def nonzero(cls, value):
        if value.int == 0:
            raise ValueError('Identificador invalido')
        return value

    @field_validator('nombre')
    @classmethod
    def valid_name(cls, value):
        value = value.strip()
        if not 1 <= len(value) <= 80 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('Usar un nombre de 1 a 80 caracteres sin controles')
        return value


def require_member(session, user, space, write=False):
    role = session.execute(text('SELECT rol FROM public.miembros_espacio WHERE usuario_id=:u AND espacio_id=:s'),
                           {'u':user, 's':space}).scalar_one_or_none()
    if role not in (('owner', 'editor') if write else ('owner', 'editor', 'lector')):
        raise HTTPException(403, 'Sin permiso para esta operacion', headers=NO_STORE)


def list_accounts(session, user, space, offset=0):
    require_member(session, user, space)
    rows = session.execute(text('SELECT id, espacio_id, nombre FROM public.cuentas WHERE espacio_id=:s ORDER BY id LIMIT 101 OFFSET :offset'),
                           {'s':space, 'offset':offset}).mappings().all()
    return {'items': [dict(row) for row in rows[:100]], 'next_offset': offset + 100 if len(rows) > 100 else None}


def create_account(session, user, space, body):
    require_member(session, user, space, write=True)
    session.execute(text('INSERT INTO public.cuentas(id, espacio_id, nombre) VALUES (:id,:s,:n) ON CONFLICT (id) DO NOTHING'),
                    {'id':body.id, 's':space, 'n':body.nombre})
    row = session.execute(text('SELECT id, espacio_id, nombre FROM public.cuentas WHERE id=:id AND espacio_id=:s'),
                          {'id':body.id, 's':space}).mappings().one_or_none()
    if row is None or row['nombre'] != body.nombre:
        raise HTTPException(409, 'El identificador ya fue usado para otra cuenta', headers=NO_STORE)
    return dict(row)


def execute(request, response, space, operation):
    identity = me(request, response)
    engine = getattr(request.app.state, 'runtime_engine', None)
    if engine is None:
        raise HTTPException(503, 'Base no disponible', headers=NO_STORE)
    try:
        with runtime_transaction(engine, usuario_id=identity['usuario_id'], espacio_id=space) as session:
            return operation(session, identity['usuario_id'])
    except SQLAlchemyError:
        raise HTTPException(503, 'No se pudo completar la operacion', headers=NO_STORE) from None


@router.get('/spaces/{space}/accounts')
def get_accounts(space: UUID, request: Request, response: Response, offset: int = Query(default=0, ge=0, le=100000)):
    return execute(request, response, space, lambda session, user: list_accounts(session, user, space, offset))


@router.post('/spaces/{space}/accounts')
def post_account(space: UUID, body: AccountInput, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: create_account(session, user, space, body))
