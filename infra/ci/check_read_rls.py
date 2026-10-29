"""Lectura RLS real; solo se invoca desde la base temporal de check_database."""
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.connection import create_runtime_engine, create_migration_engine
from app.db.unit_of_work import runtime_transaction


def check_read_rls(runtime_url, migration_url):
    runtime = create_runtime_engine(runtime_url)
    migrator = create_migration_engine(migration_url)
    user_a, user_b, outsider = (uuid4() for _ in range(3))
    space_a, space_b, shared = (uuid4() for _ in range(3))
    spaces = (space_a, space_b, shared)

    def require(value, message):
        if not value:
            raise ValueError(f"Lectura RLS: {message}")

    def visible(user, expected, selected=None):
        with runtime_transaction(runtime, usuario_id=user, espacio_id=selected) as session:
            # Intencionalmente sin WHERE: PostgreSQL debe aplicar el aislamiento.
            actual = set(session.execute(text('SELECT id FROM public.espacios')).scalars())
            members = session.execute(text('SELECT usuario_id, espacio_id FROM public.miembros_espacio')).all()
            require(actual == set(expected), 'espacios visibles incorrectos')
            require(set(members) == {(user, item) for item in expected}, 'membresias ajenas o faltantes')

    try:
        with migrator.begin() as connection:
            for table in ('espacios', 'miembros_espacio'):
                flags = connection.execute(text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid=to_regclass(:table)"), {'table': 'public.' + table}).one()
                require(flags == (True, True), f'{table} debe tener RLS y FORCE activos')
                for role in ('anon', 'authenticated', 'service_role'):
                    for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'):
                        require(not connection.execute(text('SELECT has_table_privilege(:role,:table,:privilege)'),
                            {'role':role,'table':'public.'+table,'privilege':privilege}).scalar_one(), 'grants inesperados en Data API')
                for privilege in ('INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'):
                    require(not connection.execute(text('SELECT has_table_privilege(:role,:table,:privilege)'),
                        {'role':'app_runtime','table':'public.'+table,'privilege':privilege}).scalar_one(), 'runtime tiene privilegios de escritura')
            connection.execute(text('INSERT INTO public.espacios (id,nombre) VALUES (:id,:nombre)'),
                [{'id':space_a,'nombre':'A'}, {'id':space_b,'nombre':'B'}, {'id':shared,'nombre':'Compartido'}])
            connection.execute(text('INSERT INTO public.miembros_espacio (usuario_id,espacio_id,rol) VALUES (:u,:s,:r)'),
                [{'u':user_a,'s':space_a,'r':'owner'}, {'u':user_a,'s':shared,'r':'lector'},
                 {'u':user_b,'s':space_b,'r':'owner'}, {'u':user_b,'s':shared,'r':'editor'}])
            # Backfill real sin app.*: no basta con que UPDATE termine sin error.
            updated = connection.execute(text("UPDATE public.espacios SET nombre='Backfill' WHERE id IN (:a,:b)"), {'a':space_a,'b':space_b})
            require(updated.rowcount == 2, 'backfill no actualizo dos espacios')
            require(connection.execute(text("SELECT count(*) FROM public.espacios WHERE id IN (:a,:b) AND nombre='Backfill'"),
                {'a':space_a,'b':space_b}).scalar_one() == 2, 'valores del backfill incorrectos')

        # Sin identidad válida no se ven filas. Un espacio elegido no autentica.
        with runtime.connect() as connection:
            for value in (None, ''):
                if value is not None:
                    connection.execute(text("SELECT set_config('app.user_id', '', true), set_config('app.workspace_id', :s, true)"), {'s':str(space_a)})
                for table in ('espacios', 'miembros_espacio'):
                    require(connection.execute(text(f'SELECT count(*) FROM public.{table}')).scalar_one() == 0, 'acceso sin usuario')
                connection.rollback()
            try:
                connection.execute(text("SELECT set_config('app.user_id', 'invalido', true)"))
                connection.execute(text('SELECT * FROM public.miembros_espacio')).all()
            except DBAPIError as error:
                require(error.orig.sqlstate == '22P02', 'error inesperado para contexto malformado')
            else:
                raise ValueError('Se acepto un UUID de contexto invalido')
            finally:
                connection.rollback()

        visible(user_a, (space_a, shared))
        visible(user_b, (space_b, shared))
        visible(outsider, ())
        visible(user_a, (space_a, shared), selected=space_b)
        visible(user_a, (space_a, shared), selected=space_a)
        # Listar espacios requiere usuario, no limita al espacio seleccionado.

        commands = [
            ("INSERT INTO public.espacios (id,nombre) VALUES (:id,'No permitido')", {'id':uuid4()}),
            ('UPDATE public.espacios SET nombre=\'No permitido\' WHERE id=:id', {'id':space_a}),
            ('DELETE FROM public.espacios WHERE id=:id', {'id':space_a}),
            ("INSERT INTO public.miembros_espacio (usuario_id,espacio_id,rol) VALUES (:u,:s,'owner')", {'u':outsider,'s':space_a}),
            ("UPDATE public.miembros_espacio SET rol='owner' WHERE usuario_id=:u", {'u':user_a}),
            ('DELETE FROM public.miembros_espacio WHERE usuario_id=:u', {'u':user_a}),
            ('TRUNCATE public.miembros_espacio', {}),
            ('SET ROLE app_migrator', {}),
        ]
        for sql, params in commands:
            try:
                with runtime_transaction(runtime, usuario_id=user_a, espacio_id=space_a) as session:
                    session.execute(text(sql), params)
            except DBAPIError as error:
                require(error.orig.sqlstate == '42501', 'escritura fallo por una causa distinta de permisos')
            else:
                raise ValueError('Runtime pudo administrar datos de acceso o elevar privilegios')

        with migrator.begin() as connection:
            connection.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u AND espacio_id=:s'), {'u':user_a,'s':shared})
        visible(user_a, (space_a,))
        visible(user_b, (space_b, shared))
    finally:
        try:
            with migrator.begin() as connection:
                for space in spaces:
                    connection.execute(text('DELETE FROM public.miembros_espacio WHERE espacio_id=:s'), {'s':space})
                    connection.execute(text('DELETE FROM public.espacios WHERE id=:s'), {'s':space})
        finally:
            runtime.dispose()
            migrator.dispose()
    print('OK: lectura RLS propia, espacio compartido, sin contexto, revocacion, escritura denegada y backfill.', flush=True)
