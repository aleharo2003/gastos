"""Verifica preferencias personales con RLS y el rol real de la API."""
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.connection import create_migration_engine, create_runtime_engine
from app.db.unit_of_work import runtime_transaction
from app.push_subscriptions import DevicePush, read_push, save_push
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
        custom = DEFAULTS | {'canal': 'email', 'hora_local': '18:45', 'dias_anticipacion': 5, 'vencidas': True, 'dia_resumen_semanal': 4}
        assert save(custom) == custom
        reader_values = DEFAULTS | {'canal': 'push', 'vencimientos': False, 'resumen_semanal': True}
        assert save(reader_values, reader) == reader_values
        assert run(read_preferences, reader, reader) == DEFAULTS
        assert run(read_preferences) == custom

        disabled = custom | {'canal': 'ninguno'}
        assert save(disabled) == disabled
        old_client = {key: value for key, value in disabled.items() if key != 'dia_resumen_semanal'}
        assert save(old_client) == disabled
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
                INSERT INTO public.preferencias_avisos
                    (usuario_id, espacio_id, canal, dias_anticipacion, hora_local, vencimientos, vencidas, resumen_semanal)
                VALUES (:other, :space, 'ninguno', 0, '00:00', true, false, false)
            """), {'other': reader, 'space': space}))
        except DBAPIError as error:
            assert error.orig.sqlstate == '42501'
        else:
            raise AssertionError('El propietario pudo crear preferencias de otro miembro')
        device = uuid4()
        sub = {'endpoint': 'https://fcm.googleapis.com/fcm/send/piggo-ci',
               'keys': {'p256dh': 'B' + 'A' * 86, 'auth': 'A' * 22}}
        active = DevicePush(device_id=device, subscription=sub)
        inactive = DevicePush(device_id=device, subscription=None)
        assert run(lambda s,u,w: read_push(s,u,w,device)) == {'active': False}
        for _ in range(2):
            assert run(lambda s,u,w: save_push(s,u,w,active)) == {'active': True}
        assert run(lambda s,u,w: read_push(s,u,w,device)) == {'active': True}
        assert run(lambda s,u,w: read_push(s,u,w,device), reader) == {'active': False}
        assert run(lambda s,u,w: save_push(s,u,w,inactive), reader) == {'active': False}
        try:
            run(lambda s,u,w: save_push(s,u,w,active), reader)
        except HTTPException as error:
            assert error.status_code == 409
        else:
            raise AssertionError('El mismo endpoint quedó vinculado a dos cuentas')
        assert run(lambda s,u,w: read_push(s,u,w,device)) == {'active': True}
        assert run(lambda s,u,w: save_push(s,u,w,inactive)) == {'active': False}
        assert run(lambda s,u,w: read_push(s,u,w,device)) == {'active': False}
        print('OK: alta push idempotente, aislamiento por miembro y baja del dispositivo.', flush=True)
    finally:
        runtime.dispose()
        migrator.dispose()
