"""Notifica el primer cruce de un límite a quien registró el gasto."""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from app.accounts import execute, require_member
from app.usd_reference import effective_rate, local_today

router = APIRouter()
CENT = Decimal('0.01')

TOTALS = text("""
    SELECT moneda, SUM(importe) AS total,
           COALESCE(SUM(importe) FILTER (WHERE id<>:id),0) AS anterior,
           COALESCE(SUM(importe) FILTER (WHERE tasa_pago IS NOT NULL),0) AS usd_fijado,
           COALESCE(SUM(round(importe*tasa_pago,2)),0) AS ars_fijado,
           COALESCE(SUM(importe) FILTER (WHERE tasa_pago IS NOT NULL AND id<>:id),0) AS usd_fijado_anterior,
           COALESCE(SUM(round(importe*tasa_pago,2)) FILTER (WHERE id<>:id),0) AS ars_fijado_anterior
    FROM public.gastos
    WHERE espacio_id=:space AND anulado_en IS NULL AND fecha>=:start AND fecha<:end
      AND (:category='' OR categoria=:category)
    GROUP BY moneda
""")


def converted_total(rows, currency, rate, *, previous=False, fixed=True):
    native = Decimal(0)
    foreign = Decimal(0)
    for row in rows:
        amount = row['anterior' if previous else 'total']
        if row['moneda'] == currency:
            native += amount
        elif row['moneda'] == 'USD' and fixed:
            suffix = '_anterior' if previous else ''
            native += row['ars_fijado' + suffix]
            foreign += amount - row['usd_fijado' + suffix]
        elif row['moneda'] in ('USD', 'ARS'):
            foreign += amount
        elif amount:
            return None
    if foreign:
        if rate is None:
            return None
        native += foreign * rate if currency == 'ARS' else foreign / rate
    return native.quantize(CENT, rounding=ROUND_HALF_UP)


def record_budget_alerts(session, user, space, expense_id, expense_date, category):
    today = local_today()
    week = today - timedelta(days=today.weekday())
    month = today.replace(day=1)
    next_month = (month + timedelta(days=32)).replace(day=1)
    if not min(week, month) <= expense_date < max(week + timedelta(days=7), next_month):
        return
    data = session.execute(text("""
        SELECT p.datos FROM public.planes_gasto p
        JOIN public.preferencias_avisos a ON a.espacio_id=p.espacio_id
        WHERE p.espacio_id=:space AND a.usuario_id=:user AND a.exceso_presupuesto
    """), {'space': space, 'user': user}).scalar_one_or_none()
    if data is None:
        return
    limits = data['limites']
    periods = [
        ('diario', today, today + timedelta(days=1), '', limits.get('diario')),
        ('semanal', week, week + timedelta(days=7), '', limits.get('semanal')),
        ('mensual', month, next_month, '', limits.get('mensual')),
    ]
    periods += [('mensual', month, next_month, category, limit)
                for limit in data.get('limites_categoria', []) if limit['categoria'] == category]
    checks = [(period, start, end, key, limit) for period, start, end, key, limit in periods
              if limit is not None and start <= expense_date < end]
    if not checks:
        return
    # Leer los saldos luego del bloqueo permite incluir los gastos concurrentes que ya se confirmaron.
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                    {'key': f'avisos-presupuesto:{space}'})
    quote = effective_rate(session, space, today)['cotizacion']
    rate = Decimal(quote['tasa']) if quote else None
    for period, start, end, key, limit in checks:
        rows = session.execute(TOTALS, {'id': expense_id, 'space': space, 'start': start,
                                        'end': end, 'category': key}).mappings().all()
        currency = limit['moneda']
        before = converted_total(rows, currency, rate, previous=True, fixed=not key)
        after = converted_total(rows, currency, rate, fixed=not key)
        cap = Decimal(limit['importe'])
        if before is None or after is None or not before <= cap < after:
            continue
        session.execute(text("""
            INSERT INTO public.avisos_presupuesto (id, usuario_id, espacio_id, periodo, desde, categoria, moneda, exceso)
            VALUES (:id, :user, :space, :period, :start, :category, :currency, :excess)
            ON CONFLICT (usuario_id, espacio_id, periodo, desde, categoria) DO NOTHING
        """), {'id': uuid4(), 'user': user, 'space': space, 'period': period, 'start': start,
               'category': key, 'currency': currency, 'excess': after - cap})


def list_budget_alerts(session, user, space):
    require_member(session, user, space)
    rows = session.execute(text("""
        SELECT n.id, n.periodo, n.desde, n.categoria, n.moneda, n.exceso
        FROM public.avisos_presupuesto n
        JOIN public.preferencias_avisos p USING (usuario_id, espacio_id)
        WHERE n.espacio_id=:space AND n.usuario_id=:user AND NOT n.leida AND p.exceso_presupuesto
        ORDER BY n.desde DESC, n.periodo, n.categoria, n.id LIMIT 10
    """), {'space': space, 'user': user}).mappings().all()
    return {'items': [dict(row) | {'exceso': format(row['exceso'], '.2f')} for row in rows]}


class ReadBudgetAlert(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID


def dismiss_budget_alert(session, user, space, identifier):
    require_member(session, user, space)
    session.execute(text("""
        UPDATE public.avisos_presupuesto SET leida=true
        WHERE espacio_id=:space AND usuario_id=:user AND id=:id AND NOT leida
    """), {'space': space, 'user': user, 'id': identifier})
    return list_budget_alerts(session, user, space)


@router.get('/spaces/{space}/spending-plan/alerts')
def get_alerts(space: UUID, request: Request, response: Response):
    return execute(request, response, space, lambda s, u: list_budget_alerts(s, u, space))


@router.post('/spaces/{space}/spending-plan/alerts')
def dismiss_alert(space: UUID, body: ReadBudgetAlert, request: Request, response: Response):
    return execute(request, response, space, lambda s, u: dismiss_budget_alert(s, u, space, body.id))
