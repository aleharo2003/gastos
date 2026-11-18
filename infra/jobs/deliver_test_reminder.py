"""Punto de entrada del piloto para una cuenta y un espacio explícitos."""
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from psycopg import Connection

from deliver_reminder_email import DeliveryOutcome, ResendSender, deliver_reminder_email
from verified_reminder_recipient import verified_reminder_recipient


def deliver_test_reminder(
    connection: Connection,
    instant: datetime,
    scope: tuple[UUID, UUID],
    *,
    project_ref: str,
    public_key: str,
    access_token: str,
    expected_email: str,
    app_url: str,
    sender: ResendSender,
    ars_per_usd: Mapping[UUID, Decimal] | None = None,
) -> DeliveryOutcome | None:
    address = verified_reminder_recipient(project_ref, public_key, access_token, scope[0], expected_email)
    if address is None:
        return None
    return deliver_reminder_email(connection, instant, scope, address, app_url, sender, ars_per_usd)
