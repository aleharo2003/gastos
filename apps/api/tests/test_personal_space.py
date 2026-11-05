import unittest
from unittest.mock import patch, MagicMock
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.personal_space import router

class PersonalSpaceTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        self.app = app
        self.client = TestClient(app)

    def test_requires_authenticated_identity(self):
        self.assertEqual(self.client.post('/personal-space').status_code, 401)

    def test_database_disabled(self):
        with patch('app.personal_space.me', return_value={'usuario_id': str(uuid4())}):
            result = self.client.post('/personal-space')
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.headers['cache-control'], 'no-store')

    def test_uses_verified_identity_not_body(self):
        user = str(uuid4())
        self.app.state.runtime_engine = object()
        session = MagicMock()
        session.execute.return_value.scalar_one.side_effect = [user, 'Mi espacio']
        with patch('app.personal_space.me', return_value={'usuario_id': user}), patch('app.personal_space.runtime_transaction') as transaction:
            transaction.return_value.__enter__.return_value = session
            result = self.client.post('/personal-space', json={'usuario_id': str(uuid4())})
            transaction.assert_called_once_with(self.app.state.runtime_engine, usuario_id=user)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), {'usuario_id':user,'espacio_id':user,'nombre':'Mi espacio'})
