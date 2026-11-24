"""Verifica preferencias personales con RLS y el rol real de la API."""
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.connection import create_migration_engine, create_runtime_engine
from app.db.unit_of_work import runtime_transaction
from app.reminder_preferences import DEFAULTS, ReminderPreferences, read_preferences, save_preferences


def check_reminder_preferences(runtime_url, migration_url):
    runtime = create_runtime_engine(runtime_url)
    migrator = create_migration_engine(migration_url)
    owner, reader, stranger = (uuid4() for _ in range(3))

    def run(operation, actor=owner, space=owner):
        with runtime_transaction(runtime, usuario_id=actor, espacio_id=space) as session:
            return operation(session, actor, space)

    def save(values, actor=owner, space=owner):
        body = ReminderPreferences(**values)
        return run(lambda session, user, workspace: save_preferences(session, user, workspace, body), actor, space)

    try:
        for actor in (owner, reader, stranger):
            with runtime_transaction(runtime, usuario_id=actor) as session:
                session.execute(text('SELECT public.crear_espacio_personal()'))
        with migrator.begin() as connection:
            connection.execute(text("""
                INSERT INTO public.miembros_espacio (usuario_id, espacio_id, rol)
                VALUES (:user, :space, 'lector')
            """), {'user': reader, 'space': owner})

        assert run(read_preferences) == DEFAULTS
        assert run(read_preferences, reader) == DEFAULTS
        custom = DEFAULTS | {'canal': 'email', 'hora_local': '18:45', 'dias_anticipacion': 5, 'vencidas': True}
        assert save(custom) == custom
        reader_values = DEFAULTS | {'canal': 'push', 'vencimientos': False, 'resumen_semanal': True}
        assert save(reader_values, reader) == reader_values
        assert run(read_preferences, reader, reader) == DEFAULTS
        assert run(read_preferences) == custom

        disabled = custom | {'canal': 'ninguno'}
        assert save(disabled) == disabled
        assert save(disabled) == disabled
        assert run(read_preferences) == disabled
        assert run(read_preferences, reader) == reader_values

        visible = run(lambda session, user, space: session.execute(
            text('SELECT usuario_id FROM public.preferencias_avisos'),
        ).scalars().all())
        assert visible == [owner]
        try:
            run(read_preferences, stranger)
        except HTTPException as error:
            assert error.status_code == 403
        else:
            raise AssertionError('Un tercero pudo consultar preferencias')
        try:
            run(lambda session, user, space: session.execute(text("""
                INSERT INTO public.preferencias_avisos VALUES (:other, :space, 'ninguno', 0, '00:00', true, false, false)
            """), {'other': reader, 'space': space}))
        except DBAPIError as error:
            assert error.orig.sqlstate == '42501'
        else:
            raise AssertionError('El propietario pudo crear preferencias de otro miembro')
    finally:
        runtime.dispose()
        migrator.dispose()
