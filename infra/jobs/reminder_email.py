"""Prepara el mensaje de vencimientos a partir de la cola vigente."""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from itertools import groupby
from urllib.parse import urlsplit
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row


@dataclass(frozen=True, slots=True)
class ReminderEmail:
    usuario_id: UUID
    espacio_id: UUID
    fecha_aviso: date
    asunto: str
    texto: str


def format_amount(amount: Decimal) -> str:
    return format(amount, ',.2f').translate(str.maketrans(',.', '.,'))


def format_rate(rate: Decimal) -> str:
    whole, _, fraction = format(rate, 'f').partition('.')
    fraction = fraction.rstrip('0')
    return whole + (',' + fraction if fraction else '')


def prepare_reminder_emails(
    connection: Connection,
    instant: datetime,
    app_url: str,
    ars_per_usd: Mapping[UUID, Decimal] | None = None,
    *, scope: tuple[UUID, UUID] | None = None,
) -> tuple[ReminderEmail, ...]:
    """Devuelve un mensaje por usuario y espacio para la fecha local consultada."""
    if instant.utcoffset() is None:
        raise ValueError('El instante debe incluir zona horaria')
    target = urlsplit(app_url)
    if (not app_url or any(char.isspace() or ord(char) < 32 for char in app_url)
            or target.scheme != 'https' or not target.hostname or target.username is not None
            or target.password is not None or target.query or target.fragment):
        raise ValueError('La URL de Piggo debe ser HTTPS y sin credenciales')

    with connection.cursor(row_factory=dict_row) as cursor:
        query = 'SELECT * FROM public.avisos_email_para_preparar(%s)'
        parameters: tuple[datetime | UUID, ...] = (instant,)
        if scope is not None:
            query = 'SELECT * FROM public.preparar_avisos_email_piloto(%s, %s, %s)'
            parameters = (*scope, instant)
        cursor.execute(query + ' ORDER BY usuario_id, espacio_id, fecha_aviso, vencimiento, cuota_id', parameters)
        rows = cursor.fetchall()
    rates = ars_per_usd or {}
    messages = []
    for (user, space, day), items in groupby(rows, lambda row: (
        row['usuario_id'], row['espacio_id'], row['fecha_aviso'],
    )):
        lines = []
        for item in items:
            amount = item['pendiente']
            currency = item['moneda']
            label = 'Vencida' if item['evento'] == 'vencida' else 'Vence'
            due = item['vencimiento'].strftime('%d/%m/%Y')
            name = ' '.join(item['nombre'].split())
            entry = f"- {label} {due} · {name} · Cuota {item['numero']} · Pendiente: {currency} {format_amount(amount)}"
            if item['estimado']:
                entry += ' (importe estimado)'
            if item['pendiente_ajuste']:
                entry += ' (pendiente de ajuste)'
            if currency == 'USD':
                rate = rates.get(space)
                if rate is None:
                    entry += ' · Sin cotización de referencia'
                else:
                    if not rate.is_finite() or rate <= 0:
                        raise ValueError('La cotización de referencia debe ser positiva')
                    equivalent = (amount * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    entry += f' · Estimado en ARS: {format_amount(equivalent)} (1 USD = ARS {format_rate(rate)})'
            lines.append(entry)

        text = '\n'.join(['Tenés cuotas pendientes en Piggo.', '', *lines, '', f'Ver en Piggo: {app_url}'])
        subject = f'Piggo · Recordatorio de cuotas del {day:%d/%m/%Y}'
        messages.append(ReminderEmail(user, space, day, subject, text))
    return tuple(messages)
