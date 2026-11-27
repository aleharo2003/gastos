"""Registro y aceptación atómica de ofertas de USD."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, StrictBool, ValidationError, field_validator
from sqlalchemy import text

from app.accounts import NO_STORE, execute, require_member
from app.incomes import IncomeInput
from app.usd_reference import ManualRate, effective_rate, local_today
from app.usd_sales import SaleInput, save_sale

router = APIRouter()


class OfferInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    ronda: UUID
    contraparte: str
    tasa: Decimal

    @field_validator('id','ronda')
    @classmethod
    def identifier(cls, value):
        return IncomeInput.identifier(value)

    @field_validator('contraparte')
    @classmethod
    def name(cls, value):
        return IncomeInput.description(value)

    @field_validator('tasa', mode='before')
    @classmethod
    def rate(cls, value):
        return ManualRate.positive_rate(value)


class AcceptOffer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    oferta_id: UUID
    origen_id: UUID
    destino_id: UUID
    fecha: date
    usd: Decimal
    confirmar_mejor: StrictBool = False
    confirmar_atipico: StrictBool = False

    @field_validator('fecha', mode='before')
    @classmethod
    def valid_date(cls, value):
        return IncomeInput.iso_date(value)

    @field_validator('usd', mode='before')
    @classmethod
    def valid_amount(cls, value):
        return IncomeInput.amount(value)


def lock_round(session, space, round_id):
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:lock,0))"),
                    {'lock': f'ofertas-usd:{space}:{round_id}'})


def find_offer(session, space, identifier):
    result = session.execute(text('SELECT * FROM public.ofertas_usd WHERE espacio_id=:s AND id=:id'),
                             {'s': space, 'id': identifier}).mappings()
    return result.one_or_none()


def public_offer(row):
    return {'id': str(row['id']), 'ronda': str(row['ronda']), 'estado': row['estado'],
            'fecha': row['fecha'].isoformat(), 'contraparte': row['contraparte'], 'tasa': format(row['tasa'],'.4f'),
            'referencia': format(row['referencia'],'.4f') if row['referencia'] is not None else None,
            'fecha_referencia': row['fecha_referencia'].isoformat() if row['fecha_referencia'] else None,
            'venta_id': str(row['venta_id']) if row['venta_id'] else None}


def save_offer(session, user, space, body):
    require_member(session, user, space, write=True)
    lock_round(session, space, body.ronda)
    desired = body.model_dump()
    row = find_offer(session, space, body.id)
    if row is None:
        grouped = session.execute(text("""
            SELECT estado FROM public.ofertas_usd WHERE espacio_id=:s AND ronda=:r LIMIT 101
        """), {'s': space, 'r': body.ronda}).scalars().all()
        if 'aceptada' in grouped or len(grouped) >= 100:
            raise HTTPException(409, 'La ronda está cerrada o alcanzó el máximo de ofertas', headers=NO_STORE)
        today = local_today()
        ref = effective_rate(session, space, today)['cotizacion']
        session.execute(text("""
            INSERT INTO public.ofertas_usd(espacio_id,id,ronda,contraparte,fecha,tasa,referencia,fecha_referencia)
            VALUES (:s,:id,:ronda,:contraparte,:fecha,:tasa,:rate,:day) ON CONFLICT (id) DO NOTHING
        """), desired | {'s': space, 'fecha': today, 'rate': Decimal(ref['tasa']) if ref else None,
                         'day': date.fromisoformat(ref['fecha']) if ref else None})
        row = find_offer(session, space, body.id)
    if row is None or any(row[key] != value for key, value in desired.items()):
        raise HTTPException(409, 'El identificador ya corresponde a otra oferta', headers=NO_STORE)
    return {'oferta': public_offer(row)}


def accept_offer(session, user, space, body):
    require_member(session, user, space, write=True)
    row = find_offer(session, space, body.oferta_id)
    if row is None:
        raise HTTPException(404, 'No encontramos la oferta', headers=NO_STORE)
    lock_round(session, space, row['ronda'])
    row = find_offer(session, space, body.oferta_id)
    if row['estado'] == 'rechazada':
        raise HTTPException(409, 'La ronda ya tiene otra oferta aceptada', headers=NO_STORE)
    if row['estado'] == 'vigente' and not body.confirmar_mejor:
        best = session.execute(text("""
            SELECT max(tasa) FROM public.ofertas_usd WHERE espacio_id=:s AND ronda=:r AND estado='vigente'
        """), {'s': space, 'r': row['ronda']}).scalar_one()
        if best > row['tasa']:
            raise HTTPException(409, 'Hay una oferta vigente a mejor precio', headers=NO_STORE)
    usd = format(body.usd, '.2f')
    ars = format((body.usd * row['tasa']).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), '.2f')
    try:
        sale = SaleInput(id=body.oferta_id, origen_id=body.origen_id, destino_id=body.destino_id,
                         fecha=body.fecha.isoformat(), contraparte=row['contraparte'], usd=usd, ars=ars,
                         confirmar_atipico=body.confirmar_atipico)
    except ValidationError:
        raise HTTPException(422, 'Verificá la fecha, las cuentas y el importe de la venta', headers=NO_STORE) from None
    result = save_sale(session, user, space, sale)
    if row['estado'] == 'vigente':
        session.execute(text("""
            UPDATE public.ofertas_usd SET estado=CASE WHEN id=:id THEN 'aceptada' ELSE 'rechazada' END,
                venta_id=CASE WHEN id=:id THEN :id ELSE NULL END
            WHERE espacio_id=:s AND ronda=:r AND estado='vigente'
        """), {'id': body.oferta_id, 's': space, 'r': row['ronda']})
    return {'venta': result}


@router.get('/spaces/{space}/usd-offers')
def read_offers(space: UUID, request: Request, response: Response, offset: int = Query(0, ge=0, le=100000)):
    def operation(session, user):
        require_member(session, user, space)
        rows = session.execute(text("""
            SELECT * FROM public.ofertas_usd WHERE espacio_id=:s
            ORDER BY (estado='vigente') DESC, fecha DESC, id DESC LIMIT 101 OFFSET :offset
        """), {'s': space, 'offset': offset}).mappings().all()
        return {'items': [public_offer(row) for row in rows[:100]], 'next_offset': offset + 100 if len(rows) > 100 else None}
    return execute(request, response, space, operation)


@router.post('/spaces/{space}/usd-offers')
def write_offer(space: UUID, body: OfferInput | AcceptOffer, request: Request, response: Response):
    return execute(request, response, space, lambda session, user: (
        accept_offer(session, user, space, body) if isinstance(body, AcceptOffer)
        else save_offer(session, user, space, body)))
