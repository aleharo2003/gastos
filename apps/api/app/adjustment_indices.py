"""Variaciones mensuales por indice y espacio."""
from datetime import date
from decimal import Decimal
import re
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import text

from app.accounts import NO_STORE, execute, require_member

router = APIRouter()
PAGE_SIZE = 100


class IndexValueInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    indice: str
    periodo: date
    variacion: Decimal

    @field_validator('indice')
    @classmethod
    def validate_index(cls, value):
        value = value.strip()
        if not 1 <= len(value) <= 80 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('Indice invalido')
        return value

    @field_validator('periodo', mode='before')
    @classmethod
    def validate_period(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', value):
            raise ValueError('Usar AAAA-MM')
        return date.fromisoformat(value + '-01')

    @field_validator('variacion', mode='before')
    @classmethod
    def validate_rate(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r'-?[0-9]{1,6}(\.[0-9]{1,4})?', value):
            raise ValueError('Usar un porcentaje con hasta cuatro decimales')
        rate = Decimal(value)
        if rate <= -100:
            raise ValueError('La variacion debe ser mayor que -100%')
        return rate


def public_value(row):
    return {
        'indice': row['indice'],
        'periodo': row['periodo'].isoformat()[:7],
        'variacion': format(row['variacion'], '.4f'),
    }


def list_index_values(session, user, space, offset):
    require_member(session, user, space)
    rows = session.execute(text("""
        SELECT indice, periodo, variacion FROM public.variaciones_indice
        WHERE espacio_id = :space
        ORDER BY periodo DESC, indice
        LIMIT :limit OFFSET :offset
    """), {'space': space, 'limit': PAGE_SIZE + 1, 'offset': offset}).mappings().all()
    return {
        'items': [public_value(row) for row in rows[:PAGE_SIZE]],
        'next_offset': offset + PAGE_SIZE if len(rows) > PAGE_SIZE and offset <= 100000 - PAGE_SIZE else None,
    }


def save_index_value(session, user, space, value):
    require_member(session, user, space, write=True)
    params = {'space': space, 'indice': value.indice, 'periodo': value.periodo, 'rate': value.variacion}
    session.execute(text("""
        INSERT INTO public.variaciones_indice (espacio_id, indice, periodo, variacion)
        VALUES (:space, :indice, :periodo, :rate)
        ON CONFLICT (espacio_id, indice, periodo) DO NOTHING
    """), params)
    row = session.execute(text("""
        SELECT indice, periodo, variacion FROM public.variaciones_indice
        WHERE espacio_id = :space AND indice = :indice AND periodo = :periodo
    """), params).mappings().one()
    if row['variacion'] != value.variacion:
        raise HTTPException(409, 'El indice ya tiene otra variacion para ese mes', headers=NO_STORE)
    return public_value(row)


@router.get('/spaces/{space}/index-values')
def get_index_values(
    space: UUID, request: Request, response: Response, offset: int = Query(0, ge=0, le=100000),
):
    return execute(request, response, space, lambda session, user: list_index_values(session, user, space, offset))


@router.post('/spaces/{space}/index-values')
def post_index_value(space: UUID, body: IndexValueInput, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: save_index_value(session, user, space, body))
