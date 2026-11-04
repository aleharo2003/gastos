from concurrent.futures import ThreadPoolExecutor
import json
import os
import time
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
import jwt

from app.auth import AuthUnavailable, InvalidToken, SigningKeys, TokenVerifier, download_keys, verifier_for
from app.main import app

ISSUER = 'https://abcdefghijklmnopqrst.supabase.co/auth/v1'


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.private = ec.generate_private_key(ec.SECP256R1())
        self.jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(self.private.public_key()))
        self.jwk.update(kid='test-key', alg='ES256', use='sig')
        self.fetch = Mock(return_value={'keys': [self.jwk]})
        self.now = 1000.0
        self.keys = SigningKeys(ISSUER + '/.well-known/jwks.json', self.fetch, lambda: self.now)
        self.verifier = TokenVerifier(ISSUER, self.keys)
        now = int(time.time())
        self.claims = dict(iss=ISSUER, aud='authenticated', sub=str(uuid4()),
            exp=now + 300, iat=now - 5, role='authenticated',
            is_anonymous=False, session_id=str(uuid4()))

    def token(self, claims=None, **headers):
        return jwt.encode(self.claims if claims is None else claims, self.private,
                          algorithm='ES256', headers={'kid': 'test-key', **headers})

    def test_valid_signature_returns_identity(self):
        self.assertEqual(self.verifier.verify(self.token()), self.claims['sub'])

    def test_wrong_claims_rejected(self):
        variants = {'iss': 'https://other.supabase.co/auth/v1', 'aud': 'anon',
            'sub': 'not-a-uuid', 'session_id': 'not-a-uuid', 'role': 'service_role',
            'is_anonymous': True, 'exp': int(time.time()) - 60,
            'nbf': int(time.time()) + 120, 'iat': int(time.time()) + 120}
        for name, value in variants.items():
            with self.subTest(name=name), self.assertRaises(InvalidToken):
                self.verifier.verify(self.token({**self.claims, name: value}))

    def test_required_claims(self):
        for name in self.claims:
            with self.subTest(name=name), self.assertRaises(InvalidToken):
                self.verifier.verify(self.token({k: v for k, v in self.claims.items() if k != name}))

    def test_claim_types_and_null_subject(self):
        for name, value in [('exp', str(self.claims['exp'])), ('is_anonymous', 'false'),
                            ('sub', '00000000-0000-0000-0000-000000000000'),
                            ('aud', ['authenticated']), ('iat', True)]:
            with self.subTest(name=name), self.assertRaises(InvalidToken):
                self.verifier.verify(self.token({**self.claims, name: value}))

    def test_wrong_signing_key(self):
        token = jwt.encode(self.claims, ec.generate_private_key(ec.SECP256R1()),
                           algorithm='ES256', headers={'kid': 'test-key'})
        with self.assertRaises(InvalidToken):
            self.verifier.verify(token)

    def test_symmetric_unsigned_malformed_and_oversized(self):
        tokens = [jwt.encode(self.claims, 'x' * 64, algorithm='HS256'),
                  jwt.encode(self.claims, '', algorithm='none'), 'invalid', 'x' * 16385]
        for token in tokens:
            with self.assertRaises(InvalidToken):
                self.verifier.verify(token)
        self.fetch.assert_not_called()

    def test_header_cannot_choose_keys_url(self):
        for field in ('jku', 'x5u', 'jwk', 'crit'):
            with self.assertRaises(InvalidToken):
                self.verifier.verify(self.token(**{field: 'https://attacker.example'}))
        self.fetch.assert_not_called()

    def test_expiry_tolerance(self):
        self.assertEqual(self.verifier.verify(self.token({**self.claims,
            'iat': int(time.time()) - 100, 'exp': int(time.time()) - 10})), self.claims['sub'])

    def test_key_cache_and_unknown_kid_throttle(self):
        self.verifier.verify(self.token())
        for kid in ('missing1', 'missing2', 'missing3'):
            with self.assertRaises(InvalidToken):
                self.verifier.verify(self.token(kid=kid))
        self.fetch.assert_called_once()

    def test_rotation_and_revocation_after_cache_ttl(self):
        self.verifier.verify(self.token())
        next_jwk = {**self.jwk, 'kid': 'next-key'}
        self.fetch.return_value = {'keys': [next_jwk]}
        self.now += 31
        self.assertEqual(self.verifier.verify(self.token(kid='next-key')), self.claims['sub'])
        with self.assertRaises(InvalidToken):
            self.verifier.verify(self.token())
        self.now += 301
        self.fetch.side_effect = AuthUnavailable()
        with self.assertRaises(AuthUnavailable):
            self.verifier.verify(self.token(kid='next-key'))

    def test_outage_keeps_only_unexpired_cached_keys(self):
        self.verifier.verify(self.token())
        self.fetch.side_effect = AuthUnavailable()
        self.now += 100
        self.assertEqual(self.verifier.verify(self.token()), self.claims['sub'])
        self.now += 201
        with self.assertRaises(AuthUnavailable):
            self.verifier.verify(self.token())
        with self.assertRaises(AuthUnavailable):
            self.verifier.verify(self.token())
        self.assertEqual(self.fetch.call_count, 2)

    def test_concurrent_requests_share_fetch(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            result = list(pool.map(lambda _: self.keys.get('test-key'), range(8)))
        self.assertEqual(len(result), 8)
        self.fetch.assert_called_once()

    def test_bad_key_documents_fail_closed(self):
        for document in ({}, {'keys': []}, {'keys': [self.jwk, self.jwk]},
                         {'keys': [{**self.jwk, 'd': 'private'}]}, {'keys': ['bad']}):
            with self.subTest(document=document), self.assertRaises(AuthUnavailable):
                SigningKeys('https://configured.example', lambda _: document).get('test-key')

    def test_project_configuration(self):
        for project in ('', 'https://attacker.example', '../other', 'UPPERCASE'):
            with self.assertRaises(AuthUnavailable):
                verifier_for(project)

    def test_http_me_valid_and_identity_headers_ignored(self):
        with patch('app.auth.verifier_for', return_value=self.verifier), TestClient(app) as client:
            result = client.get('/me', headers={'Authorization': 'Bearer ' + self.token(),
                                               'X-User-Id': str(uuid4())})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json(), {'usuario_id': self.claims['sub']})
            self.assertEqual(result.headers['cache-control'], 'no-store')
            missing = client.get('/me', headers={'X-User-Id': self.claims['sub']})
            self.assertEqual(missing.status_code, 401)

    def test_http_errors_have_no_credentials(self):
        with patch('app.auth.verifier_for', return_value=self.verifier), TestClient(app) as client:
            for authorization in ('Basic SECRET', 'Bearer SECRET', 'Bearer', 'Bearer a b'):
                result = client.get('/me', headers={'Authorization': authorization})
                self.assertEqual(result.status_code, 401)
                self.assertEqual(result.headers['www-authenticate'], 'Bearer')
                self.assertNotIn('SECRET', result.text)
            self.fetch.side_effect = AuthUnavailable()
            result = client.get('/me', headers={'Authorization': 'Bearer ' + self.token()})
            self.assertEqual(result.status_code, 503)
            self.assertEqual(result.headers['cache-control'], 'no-store')

    def test_http_duplicate_authorization(self):
        with TestClient(app) as client:
            result = client.get('/me', headers=[('Authorization', 'Bearer a'), ('Authorization', 'Bearer b')])
            self.assertEqual(result.status_code, 401)

    def test_unconfigured_auth_does_not_open_access(self):
        with patch.dict(os.environ, {}, clear=True), TestClient(app) as client:
            self.assertEqual(client.get('/health').status_code, 200)
            self.assertEqual(client.get('/me', headers={'Authorization': 'Bearer x'}).status_code, 503)


class DownloadTests(unittest.TestCase):
    def test_network_error_sanitized(self):
        import httpx
        with patch('app.auth.httpx.stream', side_effect=httpx.ConnectError('SECRET')):
            with self.assertRaises(AuthUnavailable) as caught:
                download_keys('https://configured.example')
        self.assertNotIn('SECRET', str(caught.exception))

    def test_large_response_rejected(self):
        with patch('app.auth.httpx.stream') as stream:
            response = stream.return_value.__enter__.return_value
            response.iter_bytes.return_value = [b'x' * 65537]
            with self.assertRaises(AuthUnavailable):
                download_keys('https://configured.example')
            self.assertFalse(stream.call_args.kwargs['follow_redirects'])
