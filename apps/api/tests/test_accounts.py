import unittest
from unittest.mock import patch, MagicMock
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.accounts import router, AccountInput

class AccountTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)
        self.space = str(uuid4())
        self.path = '/spaces/' + self.space + '/accounts'

    def test_requires_token(self):
        self.assertEqual(self.client.get(self.path).status_code, 401)
        self.assertEqual(self.client.post(self.path, json={'id':str(uuid4()),'nombre':'Efectivo'}).status_code, 401)

    def test_names(self):
        for name in ['', '   ', 'x'*81, 'a\nb']:
            with self.subTest(name=name), self.assertRaises(ValidationError):
                AccountInput(id=uuid4(), nombre=name)
        self.assertEqual(AccountInput(id=uuid4(), nombre=' Efectivo ').nombre, 'Efectivo')

    def test_rejects_client_identity_and_bad_pagination(self):
        result = self.client.post(self.path, json={'id':str(uuid4()),'nombre':'Efectivo','usuario_id':str(uuid4())})
        self.assertEqual(result.status_code, 422)
        self.assertEqual(self.client.get(self.path+'?offset=-1').status_code, 422)

    def test_verified_context_and_membership(self):
        user = str(uuid4())
        self.app.state.runtime_engine = object()
        session = MagicMock()
        session.execute.return_value.scalar_one_or_none.return_value = None
        with patch('app.accounts.me', return_value={'usuario_id':user}), patch('app.accounts.runtime_transaction') as tx:
            tx.return_value.__enter__.return_value = session
            result = self.client.get(self.path)
            self.assertEqual(result.status_code, 403)
            self.assertEqual(result.headers['cache-control'], 'no-store')
            self.assertEqual(tx.call_args.kwargs['usuario_id'], user)
            self.assertEqual(str(tx.call_args.kwargs['espacio_id']), self.space)
