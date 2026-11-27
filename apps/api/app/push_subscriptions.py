"""Almacena las suscripciones del dispositivo sin devolver sus credenciales."""
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.accounts import execute, NO_STORE, require_member

router = APIRouter()
PUSH_HOSTS = {'fcm.googleapis.com', 'updates.push.services.mozilla.com', 'web.push.apple.com'}
PUSH_SUFFIXES = ('.push.apple.com', '.notify.windows.com')


class PushKeys(BaseModel):
    model_config = ConfigDict(extra='forbid')
    p256dh: str = Field(pattern=r'^B[A-Za-z0-9_-]{86}$')
    auth: str = Field(pattern=r'^[A-Za-z0-9_-]{22}$')


class PushSubscription(BaseModel):
    model_config = ConfigDict(extra='forbid')
    endpoint: str = Field(max_length=2048)
    keys: PushKeys

    @field_validator('endpoint')
    @classmethod
    def provider_endpoint(cls, value):
        try:
            url = urlsplit(value)
            host = url.hostname or ''
            if (not value.isascii() or any(not 33 <= ord(char) <= 126 for char in value)
                    or '\\' in value or '#' in value or url.scheme != 'https'
                    or url.netloc != host or not url.path or url.path == '/'
                    or (host not in PUSH_HOSTS and not host.endswith(PUSH_SUFFIXES))):
                raise ValueError
        except ValueError:
            raise ValueError('Endpoint Web Push no admitido') from None
        return value


class DevicePush(BaseModel):
    model_config = ConfigDict(extra='forbid')
    device_id: UUID
    subscription: PushSubscription | None


def read_push(session, user, space, device):
    require_member(session, user, space)
    params = {'u': user, 's': space, 'd': device}
    active = session.execute(text("""
        SELECT EXISTS (SELECT FROM public.suscripciones_push WHERE usuario_id=:u AND espacio_id=:s AND dispositivo_id=:d)
    """), params).scalar_one()
    return {'active': active}


def save_push(session, user, space, body):
    require_member(session, user, space)
    params = {'u': user, 's': space, 'd': body.device_id}
    sub = body.subscription
    if sub is None:
        session.execute(text("""
            DELETE FROM public.suscripciones_push WHERE usuario_id=:u AND espacio_id=:s AND dispositivo_id=:d
        """), params)
        return {'active': False}

    try:
        session.execute(text("""
            INSERT INTO public.suscripciones_push (usuario_id, espacio_id, dispositivo_id, endpoint, p256dh, auth)
            VALUES (:u, :s, :d, :endpoint, :p256dh, :auth)
            ON CONFLICT (usuario_id, espacio_id, dispositivo_id) DO UPDATE SET
                endpoint=EXCLUDED.endpoint, p256dh=EXCLUDED.p256dh, auth=EXCLUDED.auth
        """), params | {'endpoint': sub.endpoint, **sub.keys.model_dump()})
    except IntegrityError as error:
        if getattr(error.orig, 'sqlstate', None) != '23505':
            raise
        raise HTTPException(409, 'Este dispositivo ya tiene una suscripción registrada', headers=NO_STORE) from None
    return {'active': True}


@router.get('/spaces/{space}/push-subscriptions')
def get_device(space: UUID, device: UUID, request: Request, response: Response):
    return execute(request, response, space, lambda s, u: read_push(s, u, space, device))


@router.post('/spaces/{space}/push-subscriptions')
def set_device(space: UUID, body: DevicePush, request: Request, response: Response):
    return execute(request, response, space, lambda s, u: save_push(s, u, space, body))
