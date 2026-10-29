"""Contrato de cuentas sobre el PostgreSQL desechable de CI."""
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.connection import create_migration_engine, create_runtime_engine
from app.db.unit_of_work import runtime_transaction


def check_accounts_rls(runtime_url, migration_url):
    runtime = create_runtime_engine(runtime_url)
    migrator = create_migration_engine(migration_url)
    owner, editor, reader, outsider = (uuid4() for _ in range(4))
    users = (owner, editor, reader, outsider)
    space_a, space_b, account_a, account_b = (uuid4() for _ in range(4))
    spaces = (space_a, space_b)
    insert = text('INSERT INTO public.cuentas (id,espacio_id,nombre) VALUES (:id,:s,:n)')

    def require(condition, message):
        if not condition:
            raise ValueError('RLS cuentas: ' + message)

    def visible(user, selected, expected):
        with runtime_transaction(runtime, usuario_id=user, espacio_id=selected) as session:
            # Sin WHERE: prueba independiente de filtros en repositorios futuros.
            rows = set(session.execute(text('SELECT id FROM public.cuentas')).scalars())
            require(rows == set(expected), 'filas visibles incorrectas')

    def denied(user, selected, sql, params, expected='42501'):
        try:
            with runtime_transaction(runtime, usuario_id=user, espacio_id=selected) as session:
                session.execute(text(sql), params)
        except DBAPIError as error:
            require(error.orig.sqlstate == expected, 'error diferente al esperado')
        else:
            raise ValueError('Se permitio una escritura prohibida')

    try:
        with migrator.begin() as c:
            require(c.execute(text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='public.cuentas'::regclass")).scalar_one(), 'faltan RLS o FORCE')
            for role in ('anon', 'authenticated', 'service_role'):
                for privilege in ('SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'):
                    require(not c.execute(text("SELECT has_table_privilege(:role,'public.cuentas',:privilege)"),
                        {'role':role,'privilege':privilege}).scalar_one(), 'grants inesperados a Data API')
            c.execute(text('INSERT INTO public.perfiles (usuario_id,nombre) VALUES (:u,:n)'),
                      [{'u':u,'n':'Fixture cuentas'} for u in users])
            c.execute(text('INSERT INTO public.espacios (id,nombre) VALUES (:s,:n)'),
                      [{'s':s,'n':'Fixture cuentas'} for s in spaces])
            c.execute(text('INSERT INTO public.miembros_espacio (usuario_id,espacio_id,rol) VALUES (:u,:s,:r)'),
                      [{'u':owner,'s':space_a,'r':'owner'}, {'u':owner,'s':space_b,'r':'owner'},
                       {'u':editor,'s':space_a,'r':'editor'}, {'u':reader,'s':space_a,'r':'lector'}])
            c.execute(insert,[{'id':account_a,'s':space_a,'n':'A'}, {'id':account_b,'s':space_b,'n':'B'}])
            require(c.execute(text("UPDATE public.cuentas SET nombre='Backfill' WHERE espacio_id IN (:a,:b)"),
                {'a':space_a,'b':space_b}).rowcount == 2, 'backfill omitio filas')
            require(c.execute(text("SELECT count(*) FROM public.cuentas WHERE espacio_id IN (:a,:b) AND nombre='Backfill'"),
                {'a':space_a,'b':space_b}).scalar_one() == 2, 'backfill no cambio valores')

        for user in (owner, editor, reader):
            visible(user, space_a, (account_a,))
        visible(owner, space_b, (account_b,))
        visible(owner, None, ())
        visible(editor, space_b, ())
        visible(outsider, space_a, ())
        with runtime.connect() as c:
            require(c.execute(text('SELECT count(*) FROM public.cuentas')).scalar_one() == 0, 'acceso sin contexto')

        for user in (owner, editor):
            new_id = uuid4()
            with runtime_transaction(runtime, usuario_id=user, espacio_id=space_a) as session:
                session.execute(insert, {'id':new_id,'s':space_a,'n':'Nueva'})
            with runtime_transaction(runtime, usuario_id=user, espacio_id=space_a) as session:
                require(session.execute(text("UPDATE public.cuentas SET nombre='Editada' WHERE id=:id"), {'id':new_id}).rowcount == 1,
                        'editor/owner no pudo editar')
                require(session.execute(text('SELECT nombre FROM public.cuentas WHERE id=:id'), {'id':new_id}).scalar_one() == 'Editada',
                        'la edicion no cambio el nombre')
            with runtime_transaction(runtime, usuario_id=user, espacio_id=space_a) as session:
                require(session.execute(text('DELETE FROM public.cuentas WHERE id=:id'), {'id':new_id}).rowcount == 1,
                        'editor/owner no pudo eliminar')

        for user, selected, target in ((reader,space_a,space_a), (outsider,space_a,space_a),
                                       (owner,None,space_a), (owner,space_a,space_b)):
            denied(user, selected, str(insert), {'id':uuid4(),'s':target,'n':'Prohibida'})
        with runtime_transaction(runtime, usuario_id=reader, espacio_id=space_a) as session:
            require(session.execute(text("UPDATE public.cuentas SET nombre='Prohibida' WHERE id=:id"), {'id':account_a}).rowcount == 0,
                    'lector pudo actualizar')
            require(session.execute(text('DELETE FROM public.cuentas WHERE id=:id'), {'id':account_a}).rowcount == 0,
                    'lector pudo borrar')
        # Incluso con membresía owner en ambos espacios, la operación queda en A.
        with runtime_transaction(runtime, usuario_id=owner, espacio_id=space_a) as session:
            require(session.execute(text("UPDATE public.cuentas SET nombre='Ajena' WHERE id=:id"), {'id':account_b}).rowcount == 0,
                    'se actualizo una cuenta del espacio no seleccionado')
            require(session.execute(text('DELETE FROM public.cuentas WHERE id=:id'), {'id':account_b}).rowcount == 0,
                    'se elimino una cuenta del espacio no seleccionado')
        denied(owner, space_a, 'UPDATE public.cuentas SET espacio_id=:s WHERE id=:id', {'s':space_b,'id':account_a})
        denied(owner, space_a, 'UPDATE public.cuentas SET id=:new WHERE id=:id', {'new':uuid4(),'id':account_a})
        denied(owner, space_a, 'TRUNCATE public.cuentas', {})
        with migrator.begin() as c:
            c.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u AND espacio_id=:s'), {'u':editor,'s':space_a})
        visible(editor, space_a, ())
        denied(editor, space_a, str(insert), {'id':uuid4(),'s':space_a,'n':'Revocada'})
        with migrator.connect() as c:
            require(c.execute(text('SELECT count(*) FROM public.cuentas WHERE espacio_id IN (:a,:b)'), {'a':space_a,'b':space_b}).scalar_one() == 2,
                    'las operaciones denegadas alteraron cuentas')
            require(c.execute(text("SELECT count(*) FROM public.cuentas WHERE espacio_id IN (:a,:b) AND nombre='Backfill'"),
                {'a':space_a,'b':space_b}).scalar_one() == 2, 'se modificaron cuentas protegidas')
    finally:
        try:
            with migrator.begin() as c:
                for space in spaces:
                    c.execute(text('DELETE FROM public.cuentas WHERE espacio_id=:s'), {'s':space})
                    c.execute(text('DELETE FROM public.miembros_espacio WHERE espacio_id=:s'), {'s':space})
                    c.execute(text('DELETE FROM public.espacios WHERE id=:s'), {'s':space})
                for user in users:
                    c.execute(text('DELETE FROM public.perfiles WHERE usuario_id=:u'), {'u':user})
        finally:
            migrator.dispose()
            runtime.dispose()
    print('OK: cuentas por espacio, lector sin escritura, editor/owner con escritura, revocacion y backfill.', flush=True)
