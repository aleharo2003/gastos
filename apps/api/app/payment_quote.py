"""Resuelve la cotización de un pago y expone su valor histórico."""
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from sqlalchemy import text

from app.accounts import NO_STORE
from app.usd_reference import ManualRate, effective_rate


class PaymentQuote(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fuente: Literal['referencia','ultima_venta','manual']
    tasa: Decimal | None = None

    @field_validator('tasa', mode='before')
    @classmethod
    def validate_rate(cls, value):
        return None if value is None else ManualRate.positive_rate(value)

    @model_validator(mode='after')
    def manual_only(self):
        if (self.fuente == 'manual') != (self.tasa is not None):
            raise ValueError('Indicá una tasa solo para la cotización manual')
        return self


def resolve_payment_quote(session, space, day, currency, choice):
    empty = {'tasa_pago': None, 'fuente_tasa_pago': None}
    if currency != 'USD':
        if choice is not None:
            raise HTTPException(422, 'La cotización del pago se usa en gastos en USD', headers=NO_STORE)
        return empty
    source = choice.fuente if choice else 'referencia'
    if source == 'manual':
        rate = choice.tasa
    elif source == 'ultima_venta':
        rate = session.execute(text("""
            SELECT tasa FROM public.ventas_usd WHERE espacio_id=:s AND tipo='venta' AND anulado_en IS NULL AND fecha<=:day AND tasa>0
            ORDER BY fecha DESC, registrada_en DESC NULLS LAST, id DESC LIMIT 1
        """), {'s': space, 'day': day}).scalar_one_or_none()
    else:
        quote = effective_rate(session, space, day)['cotizacion']
        rate = Decimal(quote['tasa']) if quote else None
    if rate is None:
        if choice is not None:
            raise HTTPException(422, 'La fuente elegida no tiene cotización para la fecha de pago', headers=NO_STORE)
        return empty
    return {'tasa_pago': rate, 'fuente_tasa_pago': source}


def matches_payment_quote(row, choice):
    return choice is None or (row['fuente_tasa_pago'] == choice.fuente
                              and (choice.fuente != 'manual' or row['tasa_pago'] == choice.tasa))


def public_payment_quote(row):
    rate = row.get('tasa_pago')
    if rate is None:
        return {}
    ars = (row['importe'] * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return {'tasa_pago': format(rate,'.4f'), 'fuente_tasa_pago': row['fuente_tasa_pago'],
            'importe_ars_pago': format(ars,'.2f')}
