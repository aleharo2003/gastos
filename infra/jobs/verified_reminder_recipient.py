"""Resuelve el correo confirmado de la cuenta de prueba en Supabase Auth."""
from datetime import datetime
from http.client import HTTPException, HTTPSConnection
import json
import re
from uuid import UUID

from deliver_reminder_email import mailbox

MAX_USER_RESPONSE = 64 * 1024


def verified_reminder_recipient(
    project_ref: str, public_key: str, access_token: str, expected_user: UUID, expected_email: str,
) -> str | None:
    if not re.fullmatch(r'[a-z0-9]{20}', project_ref):
        raise ValueError('Referencia de proyecto Supabase inválida')
    if not public_key or not access_token or any(
        not 33 <= ord(character) <= 126 for value in (public_key, access_token) for character in value
    ):
        raise ValueError('Configuración de Supabase Auth inválida')
    if not re.fullmatch(r'sb_publishable_[A-Za-z0-9_-]+', public_key):
        raise ValueError('La consulta de identidad requiere la clave publicable de Supabase')
    expected_address = mailbox(expected_email)

    connection = HTTPSConnection(f'{project_ref}.supabase.co', timeout=10)
    try:
        connection.request('GET', '/auth/v1/user', headers={
            'Accept': 'application/json', 'apikey': public_key,
            'Authorization': 'Bearer ' + access_token,
        })
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError('Supabase Auth no confirmó la sesión de prueba')
        raw = response.read(MAX_USER_RESPONSE + 1)
        if len(raw) > MAX_USER_RESPONSE:
            raise RuntimeError('La respuesta de Supabase Auth supera el tamaño permitido')
        data = json.loads(raw)
    except (OSError, HTTPException, ValueError):
        raise RuntimeError('No se pudo verificar la cuenta de prueba en Supabase Auth') from None
    finally:
        connection.close()

    if not isinstance(data, dict) or data.get('id') != str(expected_user):
        raise RuntimeError('La sesión de prueba pertenece a otra cuenta')
    if data.get('is_anonymous') is True:
        return None
    email = data.get('email')
    confirmed_at = data.get('email_confirmed_at')
    if not isinstance(email, str) or not isinstance(confirmed_at, str):
        return None
    try:
        confirmed = datetime.fromisoformat(confirmed_at)
        if confirmed.utcoffset() is None:
            return None
        address = mailbox(email)
    except (TypeError, ValueError):
        return None
    if address != expected_address:
        raise RuntimeError('El correo confirmado difiere del configurado para la prueba')
    return address
