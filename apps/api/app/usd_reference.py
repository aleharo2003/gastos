"""Cotización manual de referencia para la valuación de cada espacio."""
from datetime import date, datetime
from decimal import Decimal
import re
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import text

from app.accounts import execute, require_member

router = APIRouter()
RATE = re.compile(r'(?:0|[1-9][0-9]{0,7})(?:\.[0-9]{1,4})?')


MarketType = Literal['oficial', 'blue', 'bolsa', 'contadoconliqui', 'mayorista', 'cripto', 'tarjeta']


class MarketPreference(BaseModel):
    model_config = ConfigDict(extra='forbid')
    tipo: MarketType


class ManualRate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fecha: date
    tasa: Decimal

    @field_validator('fecha', mode='before')
    @classmethod
    def iso_date(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
            raise ValueError('Fecha inválida')
        return value

    @field_validator('tasa', mode='before')
    @classmethod
    def positive_rate(cls, value):
        if not isinstance(value, str) or not RATE.fullmatch(value) or Decimal(value) <= 0:
            raise ValueError('Usá una cotización positiva con hasta cuatro decimales')
        return Decimal(value)


def local_today():
    return datetime.now(ZoneInfo('America/Argentina/Buenos_Aires')).date()


def effective_rate(session, space, day):
    row = session.execute(text("""
        SELECT fecha, tasa FROM (
            SELECT fecha,tasa,1 AS prioridad FROM public.cotizaciones_manuales
            WHERE espacio_id=:space AND fecha<=:day
            UNION ALL
            SELECT fecha,tasa,0 AS prioridad FROM public.cotizaciones_mercado
            WHERE fecha<=:day AND tipo=COALESCE(
                (SELECT tipo FROM public.preferencias_cotizacion WHERE espacio_id=:space), 'oficial')
        ) AS opciones ORDER BY fecha DESC, prioridad DESC LIMIT 1
    """), {'space': space, 'day': day}).mappings().one_or_none()
    if row is None:
        return {'cotizacion': None}
    return {'cotizacion': {'fecha': row['fecha'].isoformat(), 'tasa': format(row['tasa'], '.4f')}}


def read_rate(session, user, space, day):
    require_member(session, user, space)
    return effective_rate(session, space, day)


def save_rate(session, user, space, body, day):
    require_member(session, user, space, write=True)
    session.execute(text("""
        INSERT INTO public.cotizaciones_manuales (espacio_id, fecha, tasa)
        VALUES (:space, :fecha, :tasa)
        ON CONFLICT (espacio_id, fecha) DO UPDATE SET tasa=excluded.tasa
        WHERE cotizaciones_manuales.tasa IS DISTINCT FROM excluded.tasa
    """), {'space': space, **body.model_dump()})
    return effective_rate(session, space, day)


@router.get('/spaces/{space}/usd-reference')
def get_reference(space: UUID, request: Request, response: Response, fecha: date | None = None):
    return execute(request, response, space, lambda session, user: read_rate(session, user, space, fecha or local_today()))


@router.post('/spaces/{space}/usd-reference')
def post_reference(space: UUID, body: ManualRate, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: save_rate(session, user, space, body, local_today()))

def market_type(session, user, space):
    require_member(session, user, space)
    value = session.execute(text('SELECT tipo FROM public.preferencias_cotizacion WHERE espacio_id=:s'),
                            {'s': space}).scalar_one_or_none()
    return {'tipo': value or 'oficial'}


def save_market_type(session, user, space, body):
    require_member(session, user, space, write=True)
    session.execute(text("""
        INSERT INTO public.preferencias_cotizacion (espacio_id,tipo) VALUES (:s,:tipo)
        ON CONFLICT (espacio_id) DO UPDATE SET tipo=excluded.tipo
    """), {'s': space, 'tipo': body.tipo})
    return {'tipo': body.tipo}


@router.get('/spaces/{space}/usd-reference/settings')
def get_market_type(space: UUID, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: market_type(session, user, space))


@router.post('/spaces/{space}/usd-reference/settings')
def post_market_type(space: UUID, body: MarketPreference, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: save_market_type(session, user, space, body))
