"""Migra Supabase test desde el job autorizado, antes de publicar Render."""
import os
from pathlib import Path
import re
import ssl
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'apps/api'))

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import URL
from app.db.connection import MIGRATOR, create_migration_engine, validate_connection

HOST = 'aws-1-us-west-2.pooler.supabase.com'
PROJECT = 'cyxhyfbiacfayixbmotq'
LOCK_ID = 47127009


class MigrationError(RuntimeError):
    pass


def authorized_environment(env):
    expected = {'GITHUB_ACTIONS':'true', 'GITHUB_EVENT_NAME':'push',
                'GITHUB_REF':'refs/heads/main', 'GITHUB_REPOSITORY':'aleharo2003/gastos'}
    if any(env.get(key) != value for key,value in expected.items()):
        raise MigrationError('Solo se ejecuta desde el push de main en GitHub Actions del repositorio previsto.')
    if not re.fullmatch(r'[0-9a-f]{40}', env.get('GITHUB_SHA','')):
        raise MigrationError('Falta el commit completo de GitHub Actions.')
    if not env.get('SUPABASE_MIGRATOR_PASSWORD') or not env.get('SUPABASE_DB_CA_CERT'):
        raise MigrationError('Faltan los secrets SUPABASE_MIGRATOR_PASSWORD o SUPABASE_DB_CA_CERT en test.')


def connection_url(password, certificate_path):
    # URL.create conserva caracteres especiales, sin concatenar secretos.
    return URL.create('postgresql+psycopg', username=f'app_migrator.{PROJECT}',
                      password=password, host=HOST, port=5432, database='postgres',
                      query={'sslmode':'verify-full', 'sslrootcert':str(certificate_path)})


def migrate(engine):
    """Núcleo probado contra la fixture local; el destino remoto lo fija main."""
    config = Config(str(ROOT / 'apps/api/alembic.ini'))
    heads = set(ScriptDirectory.from_config(config).get_heads())
    if len(heads) != 1:
        raise MigrationError('Se requiere una sola revision head antes de migrar test.')
    with engine.begin() as connection:
        validate_connection(connection, MIGRATOR)
        if not connection.execute(text('SELECT pg_try_advisory_xact_lock(:key)'), {'key':LOCK_ID}).scalar_one():
            raise MigrationError('Otra migracion de este flujo esta activa; no se inicio esta entrega.')
        connection.execute(text("SELECT set_config('lock_timeout','30s',true), set_config('statement_timeout','300s',true)"))
        config.attributes['connection'] = connection
        command.upgrade(config, 'head')
        command.check(config)
        applied = set(MigrationContext.configure(connection, opts={'version_table_schema':'public'}).get_current_heads())
        if applied != heads:
            raise MigrationError('La base no termino en la revision esperada.')
    # Salir del bloque confirma también la revisión; nunca usar stamp.
    return sorted(heads)[0]


def main():
    engine = None
    phase = 'configuracion'
    try:
        if len(sys.argv) != 1:
            raise MigrationError('Uso: python infra/cd/migrate_test.py, sin URL ni argumentos.')
        authorized_environment(os.environ)
        certificate = os.environ['SUPABASE_DB_CA_CERT']
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=certificate)
        with tempfile.TemporaryDirectory(prefix='gastos-test-ca-') as directory:
            path = Path(directory) / 'supabase.crt'
            with path.open('x', encoding='utf8') as f:
                os.chmod(path, 0o600)
                f.write(certificate)
            phase = 'conexion o migracion'
            engine = create_migration_engine(connection_url(os.environ['SUPABASE_MIGRATOR_PASSWORD'],path))
            try:
                revision = migrate(engine)
            finally:
                engine.dispose()
                engine = None
        print(f'OK: Supabase test en revision {revision}; migracion confirmada antes de Render.', flush=True)
        return 0
    except MigrationError as error:
        print(f'ERROR: {error}', file=sys.stderr)
    except Exception:
        # No imprimir excepciones de drivers, URLs, SQL ni el entorno.
        print(f'ERROR: fallo en {phase}; revisar secrets, certificado, conexion y migraciones. Render no debe iniciarse.', file=sys.stderr)
    finally:
        if engine is not None:
            engine.dispose()
    return 1


if __name__ == '__main__':
    sys.exit(main())
