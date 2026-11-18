"""Entrega un recordatorio reservado a través de Resend."""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from email.headerregistry import Address
from http.client import HTTPException, HTTPSConnection
import json
from typing import Literal
from uuid import UUID

from psycopg import Connection
from psycopg.pq import TransactionStatus

from reminder_email import ReminderEmail, prepare_reminder_emails

MAX_RESPONSE_BYTES = 4096


@dataclass(frozen=True, slots=True)
class DeliveryOutcome:
    estado: Literal['aceptada', 'reintento', 'incierta']
    referencia: str | None = None


def mailbox(value: str) -> str:
    address = Address(addr_spec=value)
    if not address.username or not address.domain:
        raise ValueError('Se requiere una dirección de correo completa')
    return address.addr_spec


class ResendSender:
    def __init__(self, api_key: str, from_address: str):
        if not api_key or any(not 33 <= ord(char) <= 126 for char in api_key):
            raise ValueError('Clave de Resend inválida')
        self._api_key = api_key
        self._from = mailbox(from_address)

    def send(self, attempt: UUID, recipient: str, message: ReminderEmail) -> DeliveryOutcome:
        body = json.dumps({
            'from': self._from,
            'to': [recipient],
            'subject': message.asunto,
            'text': message.texto,
        }).encode('utf-8')
        connection = HTTPSConnection('api.resend.com', timeout=10)
        try:
            connection.request('POST', '/emails', body=body, headers={
                'Authorization': 'Bearer ' + self._api_key,
                'Content-Type': 'application/json',
                'Idempotency-Key': str(attempt),
            })
            response = connection.getresponse()
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                return DeliveryOutcome('incierta')
            result = json.loads(raw)
            if isinstance(result, dict):
                if response.status in (200, 201):
                    reference = result.get('id')
                    if (isinstance(reference, str) and 1 <= len(reference.strip()) <= 255
                            and len(reference) <= 255 and all(ord(char) >= 32 for char in reference)):
                        return DeliveryOutcome('aceptada', reference)
                if response.status == 429 and result.get('name') == 'rate_limit_exceeded':
                    return DeliveryOutcome('reintento')
        except (OSError, HTTPException, ValueError):
            pass
        finally:
            connection.close()
        return DeliveryOutcome('incierta')


def deliver_reminder_email(
    connection: Connection,
    instant: datetime,
    scope: tuple[UUID, UUID],
    recipient: str,
    app_url: str,
    sender: ResendSender,
    ars_per_usd: Mapping[UUID, Decimal] | None = None,
) -> DeliveryOutcome | None:
    """Recibe la dirección del miembro mediante el ejecutor autorizado."""
    # La reserva debe quedar confirmada antes de llamar al proveedor.
    if not connection.autocommit or connection.info.transaction_status != TransactionStatus.IDLE:
        raise ValueError('La entrega requiere autocommit y una conexión sin transacción abierta')
    if instant.utcoffset() is None:
        raise ValueError('El instante debe incluir zona horaria')
    recipient = mailbox(recipient)
    with connection.transaction():
        attempt = connection.execute(
            'SELECT public.reservar_entrega_aviso_email_piloto(%s, %s, %s)', (*scope, instant),
        ).fetchone()[0]
        if attempt is None:
            return None
        messages = prepare_reminder_emails(connection, instant, app_url, ars_per_usd, scope=scope)
        if not messages:
            connection.execute(
                'SELECT public.resolver_entrega_aviso_email_piloto(%s, %s, %s)', (attempt, 'reintento', None),
            )
            return None
        (message,) = messages

    outcome = sender.send(attempt, recipient, message)
    recorded = connection.execute(
        'SELECT public.resolver_entrega_aviso_email_piloto(%s, %s, %s)',
        (attempt, outcome.estado, outcome.referencia),
    ).fetchone()[0]
    if not recorded:
        raise RuntimeError('No se pudo registrar el resultado del intento')
    return outcome
