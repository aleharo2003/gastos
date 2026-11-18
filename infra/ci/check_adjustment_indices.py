"""Ejercita el registro de porcentajes con RLS y el rol real de la API."""
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text

from app.adjustment_indices import IndexValueInput, import_index_values, list_index_values, save_index_value
from app.db.connection import create_migration_engine, create_runtime_engine
from app.db.unit_of_work import runtime_transaction


def check_adjustment_indices(runtime_url, migration_url):
    runtime = create_runtime_engine(runtime_url)
    migrator = create_migration_engine(migration_url)
    owner, other, reader = (uuid4() for _ in range(3))

    def run(operation, user=owner, space=owner):
        with runtime_transaction(runtime, usuario_id=user, espacio_id=space) as session:
            return operation(session, user, space)

    def save(rate, user=owner, space=owner, month='2026-10'):
        value = IndexValueInput(indice='CAC', periodo=month, variacion=rate)
        return run(lambda session, actor, workspace: save_index_value(session, actor, workspace, value), user, space)

    def read(user=owner, space=owner):
        return run(lambda session, actor, workspace: list_index_values(session, actor, workspace, 0), user, space)

    def import_csv(lines, user=owner, space=owner):
        csv = 'indice,periodo,variacion\n' + lines
        return run(lambda session, actor, workspace: import_index_values(session, actor, workspace, csv), user, space)

    def expect_error(status, operation):
        try:
            operation()
        except HTTPException as error:
            assert error.status_code == status
        else:
            raise AssertionError(f'Se esperaba un error HTTP {status}')

    try:
        for user in (owner, other, reader):
            with runtime_transaction(runtime, usuario_id=user) as session:
                session.execute(text('SELECT public.crear_espacio_personal()'))
        with migrator.begin() as connection:
            connection.execute(text("""
                INSERT INTO public.miembros_espacio (usuario_id, espacio_id, rol)
                VALUES (:user, :space, 'lector')
            """), {'user': reader, 'space': owner})

        october = {'indice': 'CAC', 'periodo': '2026-10', 'variacion': '2.3456'}
        assert save('2.3456') == october
        assert save('2.3456') == october
        expect_error(409, lambda: save('3.0000'))
        november = save('-0.5', month='2026-11')
        assert november['variacion'] == '-0.5000'
        assert read(reader) == {'items': [november, october], 'next_offset': None}
        expect_error(403, lambda: save('3', reader, month='2026-12'))
        expect_error(403, lambda: read(other, owner))
        assert read(other, other)['items'] == []
        assert save('5', other, other)['variacion'] == '5.0000'
        assert read()['items'] == [november, october]
        assert run(lambda session, actor, space: session.execute(
            text('SELECT count(*) FROM public.variaciones_indice WHERE espacio_id = :other'),
            {'other': other},
        ).scalar_one()) == 0

        batch = 'CAC,2026-10,2.3456\nCAC,2026-09,1.2345\nIPC,2026-10,2.0\n'
        assert import_csv(batch) == {'importadas': 2, 'existentes': 1}
        assert import_csv(batch) == {'importadas': 0, 'existentes': 3}
        previous = read()
        expect_error(409, lambda: import_csv('CAC,2026-08,1.0\nCAC,2026-10,99\n'))
        assert read() == previous
        expect_error(422, lambda: import_csv('CAC,2026-07,1.0\nIPC,2026-13,2.0\n'))
        assert read() == previous
        expect_error(403, lambda: import_csv(batch, reader))
        assert import_csv('CAC,2026-09,8.0\n', other, other) == {'importadas': 1, 'existentes': 0}
        assert read() == previous
    finally:
        runtime.dispose()
        migrator.dispose()
