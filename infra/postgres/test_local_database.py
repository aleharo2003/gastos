"""Pruebas del lanzador local sin Docker, base ni credenciales del usuario."""

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy.engine import URL, make_url

import local_database as local


PASSWORDS = {
    local.MIGRATOR: "prueba-migrator'@%:/\\$-ñ-1234",
    local.RUNTIME: "prueba-runtime'@%:/\\$-ñ-5678",
}
ENVIRONMENT = {'APP_MIGRATOR_PASSWORD': PASSWORDS[local.MIGRATOR],
               'APP_RUNTIME_PASSWORD': PASSWORDS[local.RUNTIME]}


def urls():
    return {
        role: URL.create('postgresql+psycopg', username=role, password=PASSWORDS[role],
                         host='127.0.0.1', port=54322, database='postgres',
                         query={'sslmode': 'disable'})
        for role in (local.MIGRATOR, local.RUNTIME)
    }


class LocalURLTests(unittest.TestCase):
    def read_urls(self, content, environ=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'supabase').mkdir()
            (root / 'supabase/config.toml').write_text(content, encoding='utf8')
            return local.local_urls(root, environ=ENVIRONMENT if environ is None else environ)

    def test_local_urls_preserve_passwords_and_use_native_postgres_port(self):
        found = self.read_urls('[db]\nport = 54322\n')
        for role, url in found.items():
            with self.subTest(role=role):
                self.assertEqual(url.drivername, 'postgresql+psycopg')
                self.assertEqual(url.username, role)
                self.assertEqual(url.host, '127.0.0.1')
                self.assertEqual(url.port, 54322)
                self.assertEqual(url.database, 'postgres')
                self.assertEqual(url.query['sslmode'], 'disable')
                self.assertEqual(make_url(url.render_as_string(hide_password=False)).password,
                                 PASSWORDS[role])

    def test_remote_urls_in_environment_and_extra_config_do_not_change_local_target(self):
        settings = ENVIRONMENT | {'DATABASE_URL': 'postgresql://postgres:secret@remote.example/other'}
        found = self.read_urls('[db]\nport = 54322\nhost = "remote.example"\n', settings)
        self.assertTrue(all(url.host == '127.0.0.1' for url in found.values()))
        self.assertTrue(all(url.username in PASSWORDS for url in found.values()))

    def test_port_must_be_an_integer_in_the_tcp_range(self):
        for value in ('0', '-1', '65536', 'true', '"54322"'):
            with self.subTest(value=value):
                with self.assertRaises(local.LocalError):
                    self.read_urls(f'[db]\nport = {value}\n')
        self.assertEqual(self.read_urls('[db]\nport = 1\n')[local.MIGRATOR].port, 1)
        self.assertEqual(self.read_urls('[db]\nport = 65535\n')[local.MIGRATOR].port, 65535)

    def test_missing_or_malformed_configuration_fails_without_reading_a_real_secret_file(self):
        for content in ('[db]\n', 'project_id = "gastos"\n', 'invalid = [\n'):
            with self.subTest(content=content):
                with self.assertRaises(local.LocalError):
                    self.read_urls(content)


class LocalCommandTests(unittest.TestCase):
    def call_main(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(local.sys, 'argv', ['local_database.py', *arguments]), redirect_stdout(stdout), redirect_stderr(stderr):
            result = local.main()
        return result, stdout.getvalue(), stderr.getvalue()

    def test_stamp_downgrade_and_unknown_commands_are_rejected_before_loading_credentials(self):
        for command in ('stamp', 'downgrade', 'unknown'):
            with self.subTest(command=command), patch.object(local, 'local_urls') as load, patch.object(local.subprocess, 'run') as run:
                result, _, _ = self.call_main(['alembic', command])
                self.assertEqual(result, 1)
                load.assert_not_called()
                run.assert_not_called()

    def test_missing_alembic_command_and_extra_check_arguments_are_rejected(self):
        for arguments in (['alembic'], ['check', 'extra']):
            with self.subTest(arguments=arguments), patch.object(local, 'local_urls') as load:
                self.assertEqual(self.call_main(arguments)[0], 1)
                load.assert_not_called()

    def test_alembic_receives_only_migrator_url_in_environment_and_preserves_exit_code(self):
        arguments = ['revision', '--autogenerate', '--rev-id', '0001', '-m', 'crea espacios']
        with patch.object(local, 'local_urls', return_value=urls()), patch.dict(os.environ, {'DATABASE_URL': 'runtime-value-to-remove'}, clear=True), patch.object(local.subprocess, 'run', return_value=subprocess.CompletedProcess([], 7)) as run:
            result, stdout, stderr = self.call_main(['alembic', *arguments])
        self.assertEqual(result, 7)
        command = run.call_args.args[0]
        settings = run.call_args.kwargs
        self.assertEqual(command[:3], [local.sys.executable, '-m', 'alembic'])
        self.assertEqual(command[-len(arguments):], arguments)
        self.assertEqual(settings['cwd'], local.API_DIR)
        self.assertNotIn('DATABASE_URL', settings['env'])
        observed = make_url(settings['env']['MIGRATION_DATABASE_URL'])
        self.assertEqual(observed.username, local.MIGRATOR)
        self.assertEqual(observed.password, PASSWORDS[local.MIGRATOR])
        for password in PASSWORDS.values():
            self.assertNotIn(password, ' '.join(command))
            self.assertNotIn(password, stdout + stderr)

    def test_check_uses_each_role_and_disposes_both_engines(self):
        migration, runtime = MagicMock(), MagicMock()
        with patch.object(local, 'local_urls', return_value=urls()), patch.object(local, 'create_migration_engine', return_value=migration), patch.object(local, 'create_runtime_engine', return_value=runtime), patch.object(local, 'validate_connection') as validate:
            result, stdout, stderr = self.call_main(['check'])
        self.assertEqual(result, 0)
        self.assertEqual([item.args[1] for item in validate.call_args_list], [local.MIGRATOR, local.RUNTIME])
        self.assertIs(validate.call_args_list[0].args[0], migration.connect.return_value.__enter__.return_value)
        self.assertIs(validate.call_args_list[1].args[0], runtime.connect.return_value.__enter__.return_value)
        migration.dispose.assert_called_once()
        runtime.dispose.assert_called_once()
        self.assertIn('app_migrator', stdout)
        self.assertIn('app_runtime', stdout)
        for password in PASSWORDS.values():
            self.assertNotIn(password, stdout + stderr)

    def test_failed_validation_disposes_engine_and_does_not_try_the_other_role(self):
        migration = MagicMock()
        with patch.object(local, 'local_urls', return_value=urls()), patch.object(local, 'create_migration_engine', return_value=migration), patch.object(local, 'create_runtime_engine') as runtime, patch.object(local, 'validate_connection', side_effect=local.DatabaseAccessError('permisos invalidos')):
            result, _, stderr = self.call_main(['check'])
        self.assertEqual(result, 1)
        self.assertIn('permisos invalidos', stderr)
        migration.dispose.assert_called_once()
        runtime.assert_not_called()

    def test_os_error_is_reported_without_raw_process_or_secret_details(self):
        with patch.object(local, 'local_urls', return_value=urls()), patch.object(local.subprocess, 'run', side_effect=OSError(PASSWORDS[local.MIGRATOR])):
            result, stdout, stderr = self.call_main(['alembic', 'current'])
        self.assertEqual(result, 1)
        self.assertNotIn(PASSWORDS[local.MIGRATOR], stdout + stderr)


if __name__ == '__main__':
    unittest.main()
