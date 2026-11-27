"""Punto de entrada del piloto para una cuenta y un espacio explícitos."""
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
import os
import sys
from uuid import UUID

from psycopg import Connection, connect

from deliver_reminder_email import DeliveryOutcome, ResendSender, deliver_reminder_email
from verified_reminder_recipient import verified_reminder_recipient
from weekly_summary_email import read_weekly_summary, send_weekly_summary


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
    connection.execute('SELECT public.encolar_avisos_email_piloto(%s, %s, %s)', (*scope, instant))
    return deliver_reminder_email(connection, instant, scope, address, app_url, sender, ars_per_usd)


def main() -> int:
    mode = os.environ.get('PILOT_MODE', 'preview')
    if mode not in ('preview', 'send', 'preview-weekly', 'send-weekly'):
        print('ERROR: modo del piloto inválido.', file=sys.stderr)
        return 1
    try:
        scope = UUID(os.environ['PILOT_USER_ID']), UUID(os.environ['PILOT_SPACE_ID'])
        auth = {
            'project_ref': os.environ['PILOT_SUPABASE_PROJECT_REF'],
            'public_key': os.environ['PILOT_SUPABASE_PUBLISHABLE_KEY'],
            'access_token': os.environ['PILOT_SUPABASE_ACCESS_TOKEN'],
            'expected_email': os.environ['PILOT_EMAIL'],
        }
        with connect(os.environ['PILOT_DATABASE_URL'], autocommit=True, connect_timeout=10) as connection:
            session, role = connection.execute('SELECT session_user, current_user').fetchone()
            if (session, role) != ('app_email_jobs', 'app_email_jobs'):
                raise RuntimeError('Rol del piloto inválido')
            connection.execute("SET statement_timeout = '30s'")
            instant = datetime.now(UTC)
            if mode in ('preview-weekly', 'send-weekly'):
                address = verified_reminder_recipient(expected_user=scope[0], **auth)
                if address is None:
                    raise RuntimeError('Cuenta de prueba sin correo confirmado')
                if mode == 'preview-weekly':
                    report = read_weekly_summary(connection, instant, scope)
                    print('Vista previa: resumen semanal preparado.' if report else 'Resumen semanal desactivado.')
                    return 0
                sender = ResendSender(os.environ['RESEND_API_KEY'], os.environ['PILOT_FROM_EMAIL'])
                outcome = send_weekly_summary(connection, instant, scope, address, os.environ['PILOT_APP_URL'], sender)
                if outcome is None:
                    print('Sin envío: revisá la preferencia, el día y la hora de envío o si ya se procesó esta semana.')
                    return 0
                print(f'Estado del resumen semanal: {outcome.estado}.')
                return 0 if outcome.estado == 'aceptada' else 1
            if mode == 'preview':
                if verified_reminder_recipient(expected_user=scope[0], **auth) is None:
                    raise RuntimeError('Cuenta de prueba sin correo confirmado')
                count = connection.execute('SELECT public.previsualizar_avisos_email_piloto(%s, %s, %s)',
                                           (*scope, instant)).fetchone()[0]
                print(f'Vista previa: {count} cuotas elegibles.')
                return 0
            sender = ResendSender(os.environ['RESEND_API_KEY'], os.environ['PILOT_FROM_EMAIL'])
            outcome = deliver_test_reminder(
                connection, instant, scope, app_url=os.environ['PILOT_APP_URL'], sender=sender, **auth,
            )
            if outcome is None:
                print('Sin envío: no hay recordatorio elegible o la cuenta requiere confirmación.')
                return 0
            print(f'Estado del intento: {outcome.estado}.')
            return 0 if outcome.estado == 'aceptada' else 1
    except Exception:
        print('ERROR: revisar configuración, sesión, permisos y elegibilidad del piloto.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
