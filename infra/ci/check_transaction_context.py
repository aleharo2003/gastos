"""Pruebas reales sobre la base desechable creada por check_database.py."""
from asyncio import CancelledError
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, InvalidRequestError

from app.db.connection import create_runtime_engine, create_migration_engine, DatabaseAccessError
from app.db.unit_of_work import runtime_transaction


CONTEXT = text("""
    SELECT pg_backend_pid(),
           nullif(current_setting('app.user_id', true), ''),
           nullif(current_setting('app.workspace_id', true), '')
""")


def check_transaction_context(runtime_url, migration_url):
    runtime = create_runtime_engine(runtime_url)
    migrator = create_migration_engine(migration_url)
    user_a, user_b, space_a, space_b = (uuid4() for _ in range(4))

    def require(condition, description):
        if not condition:
            raise ValueError(f"Contexto transaccional: {description}")

    def clean(pid):
        with runtime.connect() as connection:
            current_pid, user, workspace = connection.execute(CONTEXT).one()
            require(current_pid == pid, 'la prueba debe reutilizar la misma conexion fisica')
            require(user is None and workspace is None, 'quedo identidad fuera de la transaccion')

    try:
        with runtime_transaction(runtime, usuario_id=user_a, espacio_id=space_a) as session:
            pid, user, workspace = session.execute(CONTEXT).one()
            require((user, workspace) == (str(user_a), str(space_a)), 'contexto A incorrecto')
        clean(pid)
        try:
            with session.begin():
                session.execute(text('SELECT 1'))
        except InvalidRequestError:
            pass
        else:
            raise ValueError('Se reutilizo una sesion que debia estar cerrada')

        with runtime_transaction(runtime, usuario_id=user_b, espacio_id=space_b) as session:
            current_pid, user, workspace = session.execute(CONTEXT).one()
            require(current_pid == pid, 'B no reutilizo la conexion de A')
            require((user, workspace) == (str(user_b), str(space_b)), 'B heredo el contexto de A')
        clean(pid)

        with runtime_transaction(runtime, usuario_id=user_a) as session:
            current_pid, user, workspace = session.execute(CONTEXT).one()
            require(current_pid == pid and user == str(user_a) and workspace is None,
                    'operacion sin espacio seleccionado conserva un espacio anterior')
        clean(pid)

        for failure in (RuntimeError, CancelledError):
            try:
                with runtime_transaction(runtime, usuario_id=user_a, espacio_id=space_a) as session:
                    require(session.execute(CONTEXT).one()[0] == pid, 'no se reutilizo la conexion')
                    raise failure('interrupcion simulada de la operacion')
            except failure:
                pass
            else:
                raise ValueError('Se oculto una interrupcion')
            clean(pid)

        try:
            with runtime_transaction(runtime, usuario_id=user_a, espacio_id=space_a) as session:
                session.execute(text('SELECT 1 / 0'))
        except DBAPIError as error:
            require(error.orig.sqlstate == '22012', 'error SQL inesperado')
        else:
            raise ValueError('No se propago el error SQL')
        clean(pid)

        with runtime_transaction(runtime, usuario_id=user_b, espacio_id=space_b) as session:
            require(session.execute(CONTEXT).one() == (pid, str(user_b), str(space_b)),
                    'la conexion no se recupero despues del error SQL')
        clean(pid)

        try:
            with runtime_transaction(migrator, usuario_id=user_a):
                raise ValueError('Se acepto el rol de migraciones para una operacion runtime')
        except DatabaseAccessError:
            pass
    finally:
        runtime.dispose()
        migrator.dispose()
    print('OK: contexto local, misma conexion tras commit, excepcion, cancelacion simulada y error SQL.', flush=True)
