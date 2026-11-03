from pathlib import Path
import tempfile
import traceback
import unittest
from unittest.mock import MagicMock, patch

from app.db.connection import DatabaseAccessError, DatabaseConfigurationError
from app.db.startup import connect_runtime, safe_diagnostic


class RuntimeDiagnosticsTests(unittest.TestCase):
    def test_known_errors_do_not_include_original_text(self):
        cases = [
            (RuntimeError('password authentication failed SECRET'), 'AUTENTICACION'),
            (RuntimeError('certificate verify failed SECRET'), 'TLS'),
            (RuntimeError('server certificate does not match host name SECRET'), 'TLS'),
            (RuntimeError('could not translate host name SECRET'), 'DNS'),
            (RuntimeError('connection timed out SECRET'), 'TIEMPO_AGOTADO'),
            (DatabaseAccessError('SECRET'), 'PERMISOS'),
            (DatabaseConfigurationError('SECRET'), 'CONFIGURACION_ROL'),
            (RuntimeError('SECRET'), 'FALLO'),
        ]
        for error, code in cases:
            with self.subTest(code=code):
                result = safe_diagnostic(error, 'conexion')
                self.assertTrue(result.startswith(code + ':'))
                self.assertNotIn('SECRET', result)

    def test_sqlstate_authentication(self):
        for state in ('28P01', '28000'):
            error = RuntimeError('SECRET')
            error.sqlstate = state
            wrapper = RuntimeError('SECRET wrapper')
            wrapper.orig = error
            self.assertTrue(safe_diagnostic(wrapper, 'conexion').startswith('AUTENTICACION:'))

    def test_missing_settings_names_without_values(self):
        with self.assertRaises(RuntimeError) as caught:
            connect_runtime({'APP_DB_ENABLED': 'true', 'APP_DB_PASSWORD': 'SECRET'})
        self.assertIn('APP_DB_HOST', str(caught.exception))
        self.assertNotIn('SECRET', str(caught.exception))

    def test_invalid_pem_fails_before_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            cert = Path(directory) / 'ca.crt'
            cert.write_text('invalid PEM SECRET')
            env = dict(APP_DB_ENABLED='true', APP_DB_HOST='host',
                       APP_DB_USER='app_runtime.ref', APP_DB_PASSWORD='SECRET',
                       APP_DB_CA_FILE=str(cert))
            with patch('app.db.startup.create_runtime_engine') as create:
                with self.assertRaises(RuntimeError) as caught:
                    connect_runtime(env)
                self.assertIn('CERTIFICADO:', str(caught.exception))
                create.assert_not_called()

    def test_failed_connection_reports_phase_without_traceback_secrets(self):
        engine = MagicMock()
        engine.connect.side_effect = RuntimeError('SECRET credentials')
        engine.dispose.side_effect = RuntimeError('SECRET cleanup')
        with patch('app.db.startup.configured_url', return_value='url'), \
             patch('app.db.startup.validate_certificate'), \
             patch('app.db.startup.create_runtime_engine', return_value=engine):
            try:
                connect_runtime({})
            except RuntimeError:
                rendered = traceback.format_exc()
            else:
                self.fail('Debe fallar')
        self.assertIn('etapa=conexion', rendered)
        self.assertNotIn('SECRET credentials', rendered)
        self.assertNotIn('SECRET cleanup', rendered)
        engine.dispose.assert_called_once()
