"""Entrega avisos de vencimiento sin incluir datos financieros en la pantalla bloqueada."""
import os
import sys
from urllib.parse import urlsplit

import psycopg
import requests
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

from generate_month import verify_jobs_role

RESERVE = 'SELECT * FROM public.reservar_aviso_push()'
RESOLVE = 'SELECT public.resolver_aviso_push(%s,%s,%s,%s,%s)'
PAYLOAD = '{"type":"due"}'


class PushHttpSession(requests.Session):
    def request(self, method, url, **kwargs):
        # La validación se repite en el punto de salida y se evita seguir redirecciones.
        target = urlsplit(url)
        host = target.hostname or ''
        if (target.scheme != 'https' or target.netloc != host or '\\' in url or '#' in url
                or (host not in {'fcm.googleapis.com', 'updates.push.services.mozilla.com', 'web.push.apple.com'}
                    and not host.endswith(('.push.apple.com', '.notify.windows.com')))):
            raise ValueError('Proveedor push no admitido')
        kwargs['allow_redirects'] = False
        return super().request(method, url, **kwargs)


def send_push(http, endpoint, public_key, secret, private_key, contact, send=webpush):
    try:
        response = send(
            subscription_info={'endpoint': endpoint, 'keys': {'p256dh': public_key, 'auth': secret}},
            data=PAYLOAD, vapid_private_key=private_key, vapid_claims={'sub': contact},
            ttl=900, timeout=6, requests_session=http,
        )
    except WebPushException as error:
        response = error.response
    except (requests.RequestException, ValueError):
        response = None
    code = response.status_code if response is not None else None
    if code in (404, 410):
        return 'vencido'
    if code == 429:
        return 'reintento'
    return 'aceptado' if code is not None and 200 <= code < 300 else 'incierto'


def deliver(connection, http, private_key, contact, *, limit=30, send=webpush):
    if not connection.autocommit:
        raise ValueError('Se debe confirmar cada reserva antes del envío')
    results = {key: 0 for key in ('aceptado', 'vencido', 'reintento', 'incierto')}
    with connection.cursor() as cursor:
        verify_jobs_role(cursor)
        cursor.execute("SET statement_timeout='20s'")
        for _ in range(limit):
            cursor.execute(RESERVE)
            row = cursor.fetchone()
            if row is None:
                break
            attempt, endpoint, public_key, secret = row
            outcome = send_push(http, endpoint, public_key, secret, private_key, contact, send)
            cursor.execute(RESOLVE, (attempt, outcome, endpoint, public_key, secret))
            cursor.fetchone()
            results[outcome] += 1
    return results


def main():
    try:
        contact = os.environ['PIGGO_VAPID_CONTACT']
        if not contact.startswith('mailto:') or '@' not in contact or any(c.isspace() for c in contact):
            raise ValueError('Contacto VAPID inválido')
        private_key = os.environ['PIGGO_VAPID_PRIVATE_KEY']
        if len(private_key) != 43 or not private_key.isascii() or not all(c.isalnum() or c in '-_' for c in private_key):
            raise ValueError('Clave VAPID inválida')
        vapid = Vapid.from_raw(private_key.encode('ascii'))
        with psycopg.connect(os.environ['JOBS_DATABASE_URL'], autocommit=True, connect_timeout=10) as connection:
            with PushHttpSession() as http:
                http.trust_env = False
                results = deliver(connection, http, vapid, contact)
        print('Web Push: ' + ', '.join(f'{label}={count}' for label, count in results.items()))
        return int(bool(results['incierto'] or results['reintento']))
    except Exception:
        print('ERROR: no se confirmó la ejecución de Web Push. Revisá la configuración y el rol de tareas.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
