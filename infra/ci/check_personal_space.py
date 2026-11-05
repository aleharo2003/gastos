"""Alta real y concurrente; solo se ejecuta en la base desechable de CI."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from app.db.connection import create_runtime_engine, create_migration_engine
from app.db.unit_of_work import runtime_transaction


def check_personal_space(runtime_url, migration_url):
    runtime = create_runtime_engine(runtime_url)
    migrator = create_migration_engine(migration_url)
    user, other, collision, rollback_user = [uuid4() for _ in range(4)]
    users = [user, other, collision, rollback_user]
    def create(who):
        with runtime_transaction(runtime, usuario_id=who) as session:
            return session.execute(text('SELECT public.crear_espacio_personal()')).scalar_one()
    def denied(action):
        try:
            action()
        except DBAPIError as error:
            assert error.orig.sqlstate == '42501'
        else:
            raise AssertionError('Se permitio un alta no autorizada')
    try:
        with runtime.begin() as c:
            def no_context():
                with c.begin_nested():
                    c.execute(text('SELECT public.crear_espacio_personal()'))
            denied(no_context)
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert list(pool.map(create, [user, user])) == [user, user]
        assert create(user) == user
        assert create(other) == other
        with migrator.connect() as c:
            for table, column in [('perfiles','usuario_id'),('espacios','id'),('miembros_espacio','usuario_id')]:
                assert c.execute(text(f'SELECT count(*) FROM public.{table} WHERE {column}=:id'), {'id':user}).scalar_one() == 1
            row = c.execute(text("SELECT prosecdef, proconfig, pg_get_userbyid(proowner) FROM pg_proc WHERE oid='public.crear_espacio_personal()'::regprocedure")).one()
            assert row[0] and 'search_path=pg_catalog' in row[1] and row[2] == 'app_migrator'
            for role in ['anon','authenticated','service_role']:
                assert not c.execute(text("SELECT has_function_privilege(:role,'public.crear_espacio_personal()','EXECUTE')"), {'role':role}).scalar_one()
        with runtime_transaction(runtime, usuario_id=user) as session:
            assert session.execute(text('SELECT id FROM public.espacios')).scalars().all() == [user]
        # Una excepcion posterior revierte las tres inserciones.
        try:
            with runtime_transaction(runtime, usuario_id=rollback_user) as session:
                session.execute(text('SELECT public.crear_espacio_personal()'))
                raise RuntimeError('rollback fixture')
        except RuntimeError:
            pass
        with migrator.begin() as c:
            assert c.execute(text('SELECT count(*) FROM public.perfiles WHERE usuario_id=:u'), {'u':rollback_user}).scalar_one() == 0
            c.execute(text("INSERT INTO public.espacios(id,nombre) VALUES (:u,'Preexistente')"), {'u':collision})
            c.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u'), {'u':user})
        denied(lambda: create(collision))
        denied(lambda: create(user))  # No volver a conceder owner despues de revocar.
        with migrator.connect() as c:
            assert c.execute(text('SELECT count(*) FROM public.perfiles WHERE usuario_id=:u'), {'u':collision}).scalar_one() == 0
        print('OK: alta atomica, reintentos concurrentes, aislamiento y revocacion conservada.', flush=True)
    finally:
        with migrator.begin() as c:
            for who in users:
                c.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u'), {'u':who})
                c.execute(text('DELETE FROM public.espacios WHERE id=:u'), {'u':who})
                c.execute(text('DELETE FROM public.perfiles WHERE usuario_id=:u'), {'u':who})
        runtime.dispose()
        migrator.dispose()
