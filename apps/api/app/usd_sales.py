"""Ventas registradas como cambios de dinero entre cuentas."""
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from sqlalchemy import text

from app.accounts import execute, NO_STORE, require_member
from app.incomes import IncomeInput
from app.usd_reference import effective_rate, local_today

router = APIRouter()


class SaleInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    origen_id: UUID
    destino_id: UUID
    fecha: date
    contraparte: str
    usd: Decimal
    ars: Decimal

    @field_validator('fecha', mode='before')
    @classmethod
    def valid_date(cls, value):
        return IncomeInput.iso_date(value)

    @field_validator('usd', 'ars', mode='before')
    @classmethod
    def valid_amount(cls, value):
        return IncomeInput.amount(value)

    @field_validator('contraparte')
    @classmethod
    def name(cls, value):
        return IncomeInput.description(value)

    @model_validator(mode='after')
    def valid_sale(self):
        if not all(key.int for key in (self.id, self.origen_id, self.destino_id)) or self.origen_id == self.destino_id:
            raise ValueError('Elegí dos cuentas distintas')
        if self.fecha > local_today():
            raise ValueError('La fecha de una venta registrada no puede ser futura')
        return self


def public_sale(row):
    ref = row['referencia']
    return {
        'id': str(row['id']), 'origen_id': str(row['origen_id']), 'destino_id': str(row['destino_id']),
        'fecha': row['fecha'].isoformat(), 'contraparte': row['contraparte'],
        'usd': format(row['usd'], '.2f'), 'ars': format(row['ars'], '.2f'), 'tasa': format(row['tasa'], '.4f'),
        'referencia': format(ref, '.4f') if ref is not None else None,
        'fecha_referencia': row['fecha_referencia'].isoformat() if row['fecha_referencia'] else None,
        'diferencia_pct': format((row['ars'] / row['usd'] / ref - 1) * 100, '.2f') if ref is not None else None,
    }


def get_sale(session, space, identifier):
    return session.execute(text('SELECT * FROM public.ventas_usd WHERE espacio_id=:s AND id=:id'),
                           {'s': space, 'id': identifier}).mappings().one_or_none()


def save_sale(session, user, space, body):
    require_member(session, user, space, write=True)
    values = body.model_dump()
    current = get_sale(session, space, body.id)
    if current is None:
        accounts = session.execute(text("""
            SELECT id, moneda FROM public.cuentas WHERE espacio_id=:s AND activa
            AND id IN (:origin,:destination) ORDER BY id FOR SHARE
        """), {'s': space, 'origin': body.origen_id, 'destination': body.destino_id}).all()
        codes = {row.id: row.moneda for row in accounts}
        if len(codes) != 2 or codes.get(body.origen_id) not in (None, 'USD') or codes.get(body.destino_id) not in (None, 'ARS'):
            raise HTTPException(422, 'Elegí una cuenta para USD y una cuenta para ARS', headers=NO_STORE)
        reference = effective_rate(session, space, body.fecha)['cotizacion']
        session.execute(text("""
            INSERT INTO public.ventas_usd (espacio_id,id,origen_id,destino_id,fecha,contraparte,usd,ars,referencia,fecha_referencia)
            VALUES (:s,:id,:origen_id,:destino_id,:fecha,:contraparte,:usd,:ars,:referencia,:fecha_referencia)
            ON CONFLICT (id) DO NOTHING
        """), values | {'s': space, 'referencia': Decimal(reference['tasa']) if reference else None,
                        'fecha_referencia': date.fromisoformat(reference['fecha']) if reference else None})
        current = get_sale(session, space, body.id)
    if current is None or any(current[key] != value for key, value in values.items()):
        raise HTTPException(409, 'El identificador le corresponde a otra venta', headers=NO_STORE)
    return public_sale(current)


def list_sales(session, user, space, offset):
    require_member(session, user, space)
    rows = session.execute(text("""
        SELECT * FROM public.ventas_usd WHERE espacio_id=:s ORDER BY fecha DESC,id DESC LIMIT 101 OFFSET :offset
    """), {'s': space, 'offset': offset}).mappings().all()
    return {'items': [public_sale(row) for row in rows[:100]], 'next_offset': offset + 100 if len(rows) > 100 else None}


@router.get('/spaces/{space}/usd-sales')
def read_sales(space: UUID, request: Request, response: Response, offset: int = Query(0, ge=0, le=100000)):
    return execute(request, response, space, lambda session, user: list_sales(session, user, space, offset))


@router.post('/spaces/{space}/usd-sales')
def post_sale(space: UUID, body: SaleInput, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: save_sale(session, user, space, body))
