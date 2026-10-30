"""Permisos efectivos de objetos propios y objetos futuros en la fixture de CI."""
from sqlalchemy import text
from app.db.connection import create_migration_engine

DATA_ROLES = ('anon', 'authenticated', 'service_role')


class PrivilegeError(RuntimeError):
    pass


def assert_closed(connection, roles, *, probes=False):
    relations = connection.execute(text("""
        SELECT c.oid, c.relname, c.relkind FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relowner='app_migrator'::regrole
          AND c.relkind IN ('r','p','v','m','f','S')
    """)).mappings().all()
    routines = connection.execute(text("""
        SELECT p.oid, p.proname FROM pg_proc p
        JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public' AND p.proowner='app_migrator'::regrole
    """)).mappings().all()
    for role in roles:
        for row in relations:
            if probes and not row['relname'].startswith('gastos_ci_acl_'):
                continue
            sequence = row['relkind'] == 'S'
            function = 'has_sequence_privilege' if sequence else 'has_table_privilege'
            privileges = ('USAGE','SELECT','UPDATE') if sequence else (
                'SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN')
            for privilege in privileges:
                if connection.execute(text(f'SELECT {function}(:role, CAST(:oid AS oid), :privilege)'),
                        {'role':role,'oid':row['oid'],'privilege':privilege}).scalar_one():
                    raise PrivilegeError(f'Acceso inesperado: {role} {privilege} {row["relname"]}')
            if not sequence:
                for privilege in ('SELECT','INSERT','UPDATE','REFERENCES'):
                    if connection.execute(text('SELECT has_any_column_privilege(:role, CAST(:oid AS oid), :privilege)'),
                            {'role':role,'oid':row['oid'],'privilege':privilege}).scalar_one():
                        raise PrivilegeError(f'Acceso por columna: {role} {row["relname"]}')
        for row in routines:
            if probes and not row['proname'].startswith('gastos_ci_acl_'):
                continue
            if connection.execute(text('SELECT has_function_privilege(:role, CAST(:oid AS oid), \'EXECUTE\')'),
                    {'role':role,'oid':row['oid']}).scalar_one():
                raise PrivilegeError(f'Acceso inesperado: {role} EXECUTE {row["proname"]}')


def create_probes(c):
    c.execute(text('CREATE TABLE public.gastos_ci_acl_table (id integer)'))
    c.execute(text('CREATE SEQUENCE public.gastos_ci_acl_sequence'))
    c.execute(text('CREATE VIEW public.gastos_ci_acl_view AS SELECT id FROM public.cuentas'))
    c.execute(text("""CREATE FUNCTION public.gastos_ci_acl_function() RETURNS bigint
        LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog
        AS 'SELECT count(*) FROM public.cuentas'"""))


def check_object_privileges(migration_url):
    engine = create_migration_engine(migration_url)
    try:
        with engine.connect() as c:
            with c.begin():
                assert_closed(c, DATA_ROLES)
            tx = c.begin()
            try:
                create_probes(c)
                assert_closed(c, DATA_ROLES + ('app_runtime',), probes=True)
            finally:
                tx.rollback()
            # Probar que el control detecta la regresiÃ³n peligrosa de PUBLIC.
            tx = c.begin()
            try:
                c.execute(text('ALTER DEFAULT PRIVILEGES FOR ROLE app_migrator GRANT EXECUTE ON FUNCTIONS TO PUBLIC'))
                create_probes(c)
                try:
                    assert_closed(c, ('app_runtime',), probes=True)
                except PrivilegeError as error:
                    if str(error) != 'Acceso inesperado: app_runtime EXECUTE gastos_ci_acl_function':
                        raise
                else:
                    raise PrivilegeError('No se detecto EXECUTE heredado de PUBLIC')
            finally:
                tx.rollback()
            # Verificar que la alteraciÃ³n de defaults realmente se revirtiÃ³.
            tx = c.begin()
            try:
                create_probes(c)
                assert_closed(c, DATA_ROLES + ('app_runtime',), probes=True)
            finally:
                tx.rollback()
    finally:
        engine.dispose()
    print('OK: grants propios y defaults cerrados; tabla, vista, secuencia y funcion; regresion PUBLIC detectada.', flush=True)
