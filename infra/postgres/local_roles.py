"""Prepara y verifica roles exclusivamente en el Supabase local del repositorio."""

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = Path(__file__).resolve().parent
SECRET_FILE = ROOT / '.env.roles.local'
ROLES = ('app_migrator', 'app_runtime')
VARIABLES = ('APP_MIGRATOR_PASSWORD', 'APP_RUNTIME_PASSWORD')


class LocalError(Exception):
    """Diagnostico operativo sin credenciales."""


def run(command, *, data=None, env=None, timeout=45):
    try:
        return subprocess.run(command, input=data, env=env, text=True,
                              capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise LocalError('No se pudo completar la operacion con Docker.') from error


def container_name(root=ROOT):
    try:
        config = tomllib.loads((root / 'supabase/config.toml').read_text(encoding='utf8'))
        project = config['project_id']
        if not isinstance(project, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', project):
            raise ValueError()
        return f'supabase_db_{project}'
    except (OSError, ValueError, KeyError) as error:
        raise LocalError('Revisar project_id en supabase/config.toml.') from error


def init_secrets(path=SECRET_FILE):
    if path.exists() or path.is_symlink():
        raise LocalError('El archivo de credenciales ya existe; se conserva sin sobrescribirlo.')
    values = {name: secrets.token_urlsafe(32) for name in VARIABLES}
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf8') as output:
            output.write('# Solo desarrollo local. No subir a Git ni compartir.\n')
            for name, value in values.items():
                output.write(f'{name}={value}\n')
    except OSError as error:
        raise LocalError('No se pudo crear el archivo local de credenciales.') from error


def load_passwords(path=SECRET_FILE, environ=None):
    environ = os.environ if environ is None else environ
    values = {name: environ.get(name) for name in VARIABLES}
    if not any(value is not None for value in values.values()):
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
                raise LocalError('Las credenciales locales requieren un archivo regular con permisos 600.')
            settings = {}
            for line in path.read_text(encoding='utf8').splitlines():
                if line and not line.startswith('#'):
                    name, separator, value = line.partition('=')
                    if not separator or name not in VARIABLES or name in settings:
                        raise LocalError('El formato del archivo local de credenciales es invalido.')
                    settings[name] = value
            values = {name: settings.get(name) for name in VARIABLES}
        except OSError as error:
            raise LocalError('Faltan credenciales locales; ejecutar primero el comando init.') from error
    for name, value in values.items():
        if not isinstance(value, str) or len(value) < 16 or any(c in value for c in '\n\r\0'):
            raise LocalError(f'{name} necesita al menos 16 caracteres y una sola linea.')
    if values[VARIABLES[0]] == values[VARIABLES[1]]:
        raise LocalError('Los dos roles necesitan contraseñas diferentes.')
    return dict(zip(ROLES, (values[name] for name in VARIABLES)))


class LocalDatabase:
    def __init__(self, container):
        self.container = container

    def psql(self, role, sql, password=None):
        command = ['docker', 'exec', '-i']
        env = os.environ.copy()
        if password is not None:
            env['PGPASSWORD'] = password
            command += ['--env', 'PGPASSWORD']
        command += [self.container, 'psql', '-X', '--no-password',
                    '--set=ON_ERROR_STOP=1', '--set=VERBOSITY=terse',
                    '--tuples-only', '--no-align', '--username', role,
                    '--dbname', 'postgres']
        if password is not None:
            # TCP por la red Docker, no socket Unix ni localhost de confianza.
            command += ['--host', self.container, '--port', '5432']
        return run(command, data=sql, env=env)

    def provision(self, passwords):
        target = '/tmp/gastos-provision-roles.sql'
        copied = run(['docker', 'cp', str(SQL_DIR / 'provision-roles.sql'),
                      f'{self.container}:{target}'])
        if copied.returncode:
            raise LocalError('No se pudo copiar el script al contenedor local. Comprobar supabase start.')
        payload = ''.join(f'{passwords[role]}\n{passwords[role]}\n' for role in ROLES)
        command = ['docker', 'exec', '-i', self.container, 'psql', '-X',
                   '--no-password', '--set=ON_ERROR_STOP=1', '--username', 'postgres',
                   '--dbname', 'postgres', '--file', target]
        result = run(command, data=payload)
        if result.returncode:
            # No mostrar contexto SQL, entradas de stdin ni contraseñas.
            lines = [line for line in result.stderr.splitlines() if 'ERROR:' in line]
            detail = lines[0].split('ERROR:', 1)[1].strip() if lines else 'Revisar permisos y disponibilidad del contenedor.'
            for password in passwords.values():
                detail = detail.replace(password, '[REDACTADO]')
            raise LocalError(f'La provision fallo y no se confirmo la transaccion. {detail}')

    def check(self, passwords):
        sql = (SQL_DIR / 'check-roles.sql').read_text(encoding='utf8')
        reports = []
        for role in ROLES:
            wrong = self.psql(role, 'SELECT 1;', secrets.token_urlsafe(32))
            if wrong.returncode == 0:
                raise LocalError('La conexion TCP acepta una contraseña incorrecta; revisar pg_hba antes de continuar.')
            result = self.psql(role, sql, passwords[role])
            if result.returncode:
                raise LocalError(f'No se pudo autenticar por TCP como {role}. Revisar credenciales y contenedor.')
            try:
                report = json.loads(result.stdout)
            except ValueError as error:
                raise LocalError(f'No se pudo interpretar la comprobacion de {role}.') from error
            expected = {
                'session_user': role, 'current_user': role, 'database': 'postgres',
                'schema': 'public', 'login': True, 'superuser': False,
                'createdb': False, 'createrole': False, 'replication': False,
                'bypassrls': False, 'connect': True, 'create_schema': False,
                'usage_public': True, 'create_public': role == 'app_migrator',
                'memberships': 0,
            }
            if report != expected:
                raise LocalError(f'Los permisos efectivos de {role} no coinciden con el contrato.')
            reports.append(report)
        return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('init', 'provision', 'check'))
    args = parser.parse_args()
    try:
        if args.action == 'init':
            init_secrets()
            print('OK: credenciales locales generadas en .env.roles.local, con permisos 600.')
            return 0
        passwords = load_passwords()
        database = LocalDatabase(container_name())
        if args.action == 'provision':
            database.provision(passwords)
            print('OK: provision confirmada. Comprobando conexiones y permisos efectivos...')
        for report in database.check(passwords):
            print(f"OK: {report['current_user']}, TCP autenticado, public CREATE={report['create_public']}, BYPASSRLS=False.")
    except (LocalError, OSError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
