"""Identidad Supabase verificada; no concede permisos sobre datos."""

from functools import lru_cache
import json
import os
import re
from threading import Lock
import time
from uuid import UUID

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Request, Response


class InvalidToken(Exception):
    pass


class AuthUnavailable(Exception):
    pass


def download_keys(url):
    # URL determinada por la configuracion, nunca por headers del JWT.
    try:
        with httpx.stream('GET', url, timeout=5, follow_redirects=False) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 65536:
                    raise ValueError()
            return json.loads(body)
    except (httpx.HTTPError, ValueError):
        raise AuthUnavailable() from None


class SigningKeys:
    """Cache acotada; un kid desconocido no dispara una descarga por request."""

    def __init__(self, url, fetch=download_keys, clock=time.monotonic):
        self.url, self.fetch, self.clock = url, fetch, clock
        self.keys = {}
        self.expires = 0.0
        self.next_refresh = 0.0
        self.lock = Lock()

    def get(self, kid):
        with self.lock:
            now = self.clock()
            if now < self.expires and kid in self.keys:
                return self.keys[kid]
            if now < self.next_refresh:
                if now >= self.expires:
                    raise AuthUnavailable()
                raise InvalidToken()
            self.next_refresh = now + 30
            try:
                document = self.fetch(self.url)
                entries = document['keys']
                if not isinstance(entries, list) or not 1 <= len(entries) <= 16:
                    raise ValueError()
                keys = {}
                for entry in entries:
                    if not isinstance(entry, dict):
                        raise ValueError()
                    if (entry.get('kty'), entry.get('crv'), entry.get('alg'), entry.get('use')) != ('EC', 'P-256', 'ES256', 'sig'):
                        continue
                    key_id = entry.get('kid')
                    if not isinstance(key_id, str) or not 1 <= len(key_id) <= 200 or key_id in keys or 'd' in entry:
                        raise ValueError()
                    if 'key_ops' in entry and entry['key_ops'] != ['verify']:
                        raise ValueError()
                    keys[key_id] = jwt.PyJWK.from_dict(entry, algorithm='ES256').key
                if not keys:
                    raise ValueError()
                self.keys = keys
                self.expires = self.clock() + 300
            except (AuthUnavailable, ValueError, KeyError, TypeError, jwt.PyJWTError):
                raise AuthUnavailable() from None
            if kid not in self.keys:
                raise InvalidToken()
            return self.keys[kid]


class TokenVerifier:
    def __init__(self, issuer, keys):
        self.issuer, self.keys = issuer, keys

    def verify(self, token):
        try:
            if not isinstance(token, str) or not 1 <= len(token) <= 16384:
                raise InvalidToken()
            header = jwt.get_unverified_header(token)
            if header.get('alg') != 'ES256' or any(name in header for name in ('crit', 'jku', 'x5u', 'jwk')):
                raise InvalidToken()
            kid = header.get('kid')
            if not isinstance(kid, str) or not 1 <= len(kid) <= 200:
                raise InvalidToken()
            key = self.keys.get(kid)
            claims = jwt.decode(token, key, algorithms=['ES256'],
                issuer=self.issuer, audience='authenticated', leeway=30,
                options={'require': ['iss', 'aud', 'exp', 'iat', 'sub', 'role', 'is_anonymous', 'session_id'],
                         'strict_aud': True})
            if claims['role'] != 'authenticated' or claims['is_anonymous'] is not False:
                raise InvalidToken()
            for name in ('exp', 'iat', 'nbf'):
                if name in claims and type(claims[name]) is not int:
                    raise InvalidToken()
            if claims['exp'] <= claims['iat']:
                raise InvalidToken()
            if not isinstance(claims['sub'], str) or not isinstance(claims['session_id'], str):
                raise InvalidToken()
            user_id = UUID(claims['sub'])
            if user_id.int == 0 or UUID(claims['session_id']).int == 0:
                raise InvalidToken()
            return str(user_id)
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            raise InvalidToken() from None


@lru_cache(maxsize=4)
def verifier_for(project_ref):
    if not re.fullmatch(r'[a-z0-9]{20}', project_ref):
        raise AuthUnavailable()
    issuer = f'https://{project_ref}.supabase.co/auth/v1'
    return TokenVerifier(issuer, SigningKeys(issuer + '/.well-known/jwks.json'))


router = APIRouter()


@router.get('/me')
def me(request: Request, response: Response) -> dict[str, str]:
    headers = {'Cache-Control': 'no-store', 'WWW-Authenticate': 'Bearer'}
    values = request.headers.getlist('authorization')
    if len(values) != 1:
        raise HTTPException(401, 'No autenticado', headers=headers)
    parts = values[0].split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        raise HTTPException(401, 'No autenticado', headers=headers)
    try:
        verifier = verifier_for(os.getenv('AUTH_SUPABASE_PROJECT_REF', ''))
        user_id = verifier.verify(parts[1])
    except InvalidToken:
        raise HTTPException(401, 'No autenticado', headers=headers) from None
    except AuthUnavailable:
        raise HTTPException(503, 'Autenticacion no disponible', headers={'Cache-Control': 'no-store'}) from None
    response.headers['Cache-Control'] = 'no-store'
    return {'usuario_id': user_id}
