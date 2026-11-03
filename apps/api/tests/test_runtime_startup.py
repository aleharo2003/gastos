import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.db.startup import configured_url, connect_runtime
from app.main import app


class RuntimeStartupTests(unittest.TestCase):
    def test_disabled_without_settings(self):
        with patch('app.db.startup.create_runtime_engine') as create:
            self.assertIsNone(connect_runtime({}))
            create.assert_not_called()

    def test_partial_configuration_rejected(self):
        for env in ({'APP_DB_ENABLED': 'true'}, {'APP_DB_HOST': 'host'},
                    {'APP_DB_ENABLED': 'yes'}):
            with self.subTest(env=env), self.assertRaises(RuntimeError):
                connect_runtime(env)

    def test_url_preserves_password_and_requires_tls(self):
        with tempfile.TemporaryDirectory() as directory:
            cert = Path(directory) / 'ca.crt'
            cert.write_text('fixture')
            url = configured_url(dict(APP_DB_ENABLED='true', APP_DB_HOST='host',
                APP_DB_USER='app_runtime.ref', APP_DB_PASSWORD='a@:/%?b',
                APP_DB_CA_FILE=str(cert)))
            self.assertEqual(url.password, 'a@:/%?b')
            self.assertEqual(url.query['sslmode'], 'verify-full')
            self.assertEqual(url.port, 5432)

    def test_success_checks_effective_role(self):
        engine = MagicMock()
        with patch('app.db.startup.configured_url', return_value='url'), \
             patch('app.db.startup.create_runtime_engine', return_value=engine), \
             patch('app.db.startup.validate_connection') as validate:
            self.assertIs(connect_runtime({}), engine)
            validate.assert_called_once_with(engine.connect.return_value.__enter__.return_value, 'app_runtime')

    def test_failure_closes_engine_and_hides_driver_message(self):
        engine = MagicMock()
        with patch('app.db.startup.configured_url', return_value='url'), \
             patch('app.db.startup.create_runtime_engine', return_value=engine), \
             patch('app.db.startup.validate_connection', side_effect=ValueError('secret-password')):
            with self.assertRaises(RuntimeError) as caught:
                connect_runtime({})
            self.assertNotIn('secret-password', str(caught.exception))
            engine.dispose.assert_called_once()

    def test_lifespan_retains_engine_and_closes_on_shutdown(self):
        engine = MagicMock()
        with patch('app.db.startup.connect_runtime', return_value=engine):
            with TestClient(app) as client:
                self.assertIs(app.state.runtime_engine, engine)
                self.assertEqual(client.get('/health').json(), {'status': 'ok'})
                engine.dispose.assert_not_called()
            engine.dispose.assert_called_once()
            self.assertIsNone(app.state.runtime_engine)

    def test_startup_failure_prevents_serving(self):
        with patch('app.db.startup.connect_runtime', side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):
                with TestClient(app):
                    self.fail('No debe aceptar peticiones')

    def test_disabled_mode_keeps_skeleton_working(self):
        with patch.dict(os.environ, {}, clear=True):
            with TestClient(app) as client:
                self.assertEqual(client.get('/').json(), {'message': 'Hola desde FastAPI'})
                self.assertIsNone(app.state.runtime_engine)
