"""Inventario cerrado de relaciones públicas y pruebas de regresión en CI.

Solo se invoca desde check_database.py sobre su PostgreSQL desechable.
Las alteraciones deliberadas se revierten, incluso si la prueba falla.
"""
from sqlalchemy import text

from app.db.connection import create_migration_engine


PRIVATE_TABLES = frozenset({'espacios', 'miembros_espacio', 'perfiles', 'cuentas'})
TECHNICAL_TABLES = frozenset({'alembic_version'})


class CoverageError(RuntimeError):
    pass


def assert_coverage(connection):
    rows = connection.execute(text("""
        SELECT c.relname AS name, c.relkind AS kind,
               pg_get_userbyid(c.relowner) AS owner,
               c.relrowsecurity AS rls, c.relforcerowsecurity AS force
        FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','f')
    """)).mappings().all()
    actual = {row['name'] for row in rows}
    expected = PRIVATE_TABLES | TECHNICAL_TABLES
    if actual != expected:
        raise CoverageError(
            'Inventario public: sin clasificar=' + ','.join(sorted(actual - expected))
            + '; ausentes=' + ','.join(sorted(expected - actual)))
    for row in rows:
        if row['owner'] != 'app_migrator' or row['kind'] != 'r':
            raise CoverageError('Propietario o tipo inesperado: ' + row['name'])
        if row['name'] in PRIVATE_TABLES:
            if not row['rls']:
                raise CoverageError('Falta RLS: ' + row['name'])
            if not row['force']:
                raise CoverageError('Falta FORCE: ' + row['name'])


def check_rls_coverage(migration_url):
    engine = create_migration_engine(migration_url)
    try:
        with engine.connect() as connection:
            with connection.begin():
                assert_coverage(connection)

            def rejected_change(sql, expected_message):
                transaction = connection.begin()
                try:
                    connection.execute(text(sql))
                    try:
                        assert_coverage(connection)
                    except CoverageError as error:
                        if str(error) != expected_message:
                            raise CoverageError('La prueba negativa fallo por otra causa') from error
                    else:
                        raise CoverageError('El control no detecto la alteracion deliberada')
                finally:
                    transaction.rollback()
                with connection.begin():
                    assert_coverage(connection)

            # Nombres constantes del inventario, nunca entrada de un usuario.
            for name in sorted(PRIVATE_TABLES):
                rejected_change(
                    f'ALTER TABLE public."{name}" DISABLE ROW LEVEL SECURITY',
                    'Falta RLS: ' + name)
                rejected_change(
                    f'ALTER TABLE public."{name}" NO FORCE ROW LEVEL SECURITY',
                    'Falta FORCE: ' + name)
            rejected_change(
                'CREATE TABLE public.gastos_ci_unclassified (id integer)',
                'Inventario public: sin clasificar=gastos_ci_unclassified; ausentes=')
    finally:
        engine.dispose()
    print('OK: inventario privado, RLS y FORCE; nueve alteraciones detectadas y revertidas.', flush=True)
