"""Pruebas offline del asistente local: no acceden a Docker ni a la base."""

import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import local_roles as roles


PASSWORDS = {'app_migrator': 'solo-pruebas-migrator-1234',
             'app_runtime': 'solo-pruebas-runtime-5678'}


def completed(code=0, stdout='', stderr=''):
    return subprocess.CompletedProcess([], code, stdout, stderr)


def report(role):
    return {
        'session_user': role, 'current_user': role, 'database': 'postgres',
        'schema': 'public', 'login': True, 'superuser': False,
        'createdb': False, 'createrole': False, 'replication': False,
        'bypassrls': False, 'connect': True, 'create_schema': False,
        'usage_public': True, 'create_public': role == 'app_migrator',
        'memberships': 0,
    }


class CredentialsTests(unittest.TestCase):
    def test_init_generates_distinct_passwords_with_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env.roles.local'
            roles.init_secrets(path)
            values = roles.load_passwords(path, environ={})
            self.assertEqual(set(values), set(roles.ROLES))
            self.assertNotEqual(*values.values())
            self.assertTrue(all(len(value) >= 32 for value in values.values()))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_init_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env.roles.local'
            path.write_text('conservar', encoding='utf8')
            with self.assertRaises(roles.LocalError):
                roles.init_secrets(path)
            self.assertEqual(path.read_text(), 'conservar')

    def test_init_refuses_dangling_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'secrets'
            destination = Path(directory) / 'inexistente'
            path.symlink_to(destination)
            with self.assertRaises(roles.LocalError):
                roles.init_secrets(path)
            self.assertFalse(destination.exists())

    def test_environment_has_precedence_over_missing_file(self):
        values = roles.load_passwords(Path('/no-existe/archivo'), environ=dict(
            zip(roles.VARIABLES, PASSWORDS.values())))
        self.assertEqual(values, PASSWORDS)

    def test_partial_environment_is_not_mixed_with_file(self):
        with self.assertRaises(roles.LocalError):
            roles.load_passwords(environ={roles.VARIABLES[0]: PASSWORDS['app_migrator']})

    def test_invalid_passwords_are_rejected_without_disclosing_them(self):
        for password in ('corta', 'contraseña-larga\nfin', 'contraseña-larga\rfin',
                         'contraseña-larga\0fin'):
            with self.subTest(password_kind=repr(password[:5])):
                with self.assertRaises(roles.LocalError) as raised:
                    roles.load_passwords(environ={roles.VARIABLES[0]: password,
                                                  roles.VARIABLES[1]: PASSWORDS['app_runtime']})
                self.assertNotIn(password, str(raised.exception))

    def test_same_password_for_both_roles_is_rejected(self):
        with self.assertRaises(roles.LocalError):
            roles.load_passwords(environ=dict.fromkeys(roles.VARIABLES, 'misma-clave-larga-1234'))

    def test_insecure_file_permissions_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'secrets'
            path.write_text('APP_MIGRATOR_PASSWORD=clave-larga-prueba-1234\n')
            path.chmod(0o644)
            with self.assertRaises(roles.LocalError):
                roles.load_passwords(path, environ={})

    def test_duplicate_unknown_and_malformed_file_settings_are_rejected(self):
        contents = ('UNKNOWN=clave-larga-prueba-1234\n',
                    'APP_MIGRATOR_PASSWORD=clave-larga-prueba-1234\n' * 2,
                    'linea-sin-separador\n')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'secrets'
            for content in contents:
                with self.subTest(content_kind=content[:10]):
                    path.write_text(content)
                    path.chmod(0o600)
                    with self.assertRaises(roles.LocalError):
                        roles.load_passwords(path, environ={})

    def test_symlink_file_is_rejected_even_if_target_is_private(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'original'
            roles.init_secrets(target)
            path = Path(directory) / 'symlink'
            path.symlink_to(target)
            with self.assertRaises(roles.LocalError):
                roles.load_passwords(path, environ={})


class ConfigurationTests(unittest.TestCase):
    def test_container_name_comes_from_project_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'supabase').mkdir()
            config = root / 'supabase/config.toml'
            config.write_text('project_id = "gastos-local_1"\n')
            self.assertEqual(roles.container_name(root), 'supabase_db_gastos-local_1')

    def test_missing_invalid_and_unsafe_project_configuration_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'supabase').mkdir()
            config = root / 'supabase/config.toml'
            for content in ('project_id = 123\n', 'project_id = "x;docker"\n',
                            'project_id = ""\n', 'invalid = [\n', 'other = "x"\n'):
                config.write_text(content)
                with self.subTest(config=content):
                    with self.assertRaises(roles.LocalError):
                        roles.container_name(root)
            config.unlink()
            with self.assertRaises(roles.LocalError):
                roles.container_name(root)


class ProcessTests(unittest.TestCase):
    def test_process_errors_are_reported_without_raw_command_details(self):
        for error in (OSError('detalle-secreto'),
                      subprocess.TimeoutExpired(['docker', 'detalle-secreto'], 45)):
            with self.subTest(error=type(error).__name__):
                with patch.object(roles.subprocess, 'run', side_effect=error):
                    with self.assertRaises(roles.LocalError) as raised:
                        roles.run(['docker', 'detalle-secreto'])
                self.assertNotIn('detalle-secreto', str(raised.exception))

    def test_tcp_password_is_passed_by_environment_not_arguments(self):
        database = roles.LocalDatabase('contenedor-prueba')
        password = PASSWORDS['app_runtime']
        with patch.object(roles, 'run', return_value=completed()) as run:
            database.psql('app_runtime', 'SELECT 1;', password)
        args, kwargs = run.call_args
        command = args[0]
        self.assertNotIn(password, ' '.join(command))
        self.assertEqual(kwargs['env']['PGPASSWORD'], password)
        self.assertEqual(kwargs['data'], 'SELECT 1;')
        self.assertIn('--env', command)
        self.assertIn('PGPASSWORD', command)
        self.assertIn('--host', command)
        self.assertEqual(command[command.index('--host') + 1], 'contenedor-prueba')
        self.assertIn('-X', command)
        self.assertIn('--no-password', command)

    def test_admin_uses_local_socket_without_password_argument(self):
        with patch.object(roles, 'run', return_value=completed()) as run:
            roles.LocalDatabase('contenedor-prueba').psql('postgres', 'SELECT 1;')
        self.assertNotIn('--host', run.call_args.args[0])

    def test_provision_sends_passwords_only_as_stdin_and_in_role_order(self):
        with patch.object(roles, 'run', return_value=completed()) as run:
            roles.LocalDatabase('contenedor-prueba').provision(PASSWORDS)
        self.assertEqual(run.call_count, 2)
        first, second = run.call_args_list
        self.assertEqual(first.args[0][:2], ['docker', 'cp'])
        expected = ''.join(PASSWORDS[role] + '\n' + PASSWORDS[role] + '\n'
                           for role in roles.ROLES)
        self.assertEqual(second.kwargs['data'], expected)
        for call in run.call_args_list:
            for password in PASSWORDS.values():
                self.assertNotIn(password, ' '.join(call.args[0]))

    def test_failed_copy_does_not_execute_psql(self):
        with patch.object(roles, 'run', return_value=completed(1)) as run:
            with self.assertRaises(roles.LocalError):
                roles.LocalDatabase('contenedor-prueba').provision(PASSWORDS)
        self.assertEqual(run.call_count, 1)

    def test_provision_error_redacts_password_and_omits_context(self):
        error = ('ERROR: fallo con ' + PASSWORDS['app_runtime'] + '\n'
                 'CONTEXT: sentencia con ' + PASSWORDS['app_migrator'])
        with patch.object(roles, 'run', side_effect=[completed(), completed(1, stderr=error)]):
            with self.assertRaises(roles.LocalError) as raised:
                roles.LocalDatabase('contenedor-prueba').provision(PASSWORDS)
        message = str(raised.exception)
        self.assertIn('[REDACTADO]', message)
        self.assertNotIn('CONTEXT', message)
        for password in PASSWORDS.values():
            self.assertNotIn(password, message)


class ConnectionCheckTests(unittest.TestCase):
    def test_check_requires_bad_password_failure_and_good_password_success_for_each_role(self):
        responses = []
        for role in roles.ROLES:
            responses.extend([completed(1), completed(stdout=json.dumps(report(role)))])
        database = roles.LocalDatabase('contenedor-prueba')
        with patch.object(database, 'psql', side_effect=responses) as psql:
            self.assertEqual(database.check(PASSWORDS), [report(role) for role in roles.ROLES])
        self.assertEqual(psql.call_count, 4)
        for index, role in enumerate(roles.ROLES):
            wrong, correct = psql.call_args_list[index * 2:index * 2 + 2]
            self.assertEqual(wrong.args[0], role)
            self.assertNotEqual(wrong.args[2], PASSWORDS[role])
            self.assertEqual(correct.args[2], PASSWORDS[role])

    def test_accepted_wrong_password_aborts_check(self):
        database = roles.LocalDatabase('contenedor-prueba')
        with patch.object(database, 'psql', return_value=completed()) as psql:
            with self.assertRaises(roles.LocalError):
                database.check(PASSWORDS)
        self.assertEqual(psql.call_count, 1)

    def test_failed_good_connection_aborts_without_exposing_raw_stderr(self):
        database = roles.LocalDatabase('contenedor-prueba')
        with patch.object(database, 'psql', side_effect=[completed(1), completed(1, stderr='secreto')]):
            with self.assertRaises(roles.LocalError) as raised:
                database.check(PASSWORDS)
        self.assertNotIn('secreto', str(raised.exception))

    def test_invalid_json_is_rejected(self):
        database = roles.LocalDatabase('contenedor-prueba')
        with patch.object(database, 'psql', side_effect=[completed(1), completed(stdout='no-json')]):
            with self.assertRaises(roles.LocalError):
                database.check(PASSWORDS)

    def test_effective_privilege_or_identity_drift_is_rejected(self):
        changes = ({'bypassrls': True}, {'create_public': False}, {'memberships': 1},
                   {'session_user': 'postgres'}, {'current_user': 'postgres'})
        for change in changes:
            with self.subTest(change=change):
                changed = report('app_migrator') | change
                database = roles.LocalDatabase('contenedor-prueba')
                with patch.object(database, 'psql', side_effect=[completed(1), completed(stdout=json.dumps(changed))]):
                    with self.assertRaises(roles.LocalError):
                        database.check(PASSWORDS)


if __name__ == '__main__':
    unittest.main()
