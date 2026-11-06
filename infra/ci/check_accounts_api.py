"""Contrato de cuentas contra PostgreSQL real en la fixture de CI."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import text
from app.accounts import AccountInput, create_account, list_accounts
from app.db.connection import create_runtime_engine, create_migration_engine
from app.db.unit_of_work import runtime_transaction


def check_accounts_api(runtime_url, migration_url):
    runtime, migrator = create_runtime_engine(runtime_url), create_migration_engine(migration_url)
    owner, other, reader = [uuid4() for _ in range(3)]
    account = AccountInput(id=uuid4(), nombre='Efectivo')
    users = [owner, other, reader]
    def create(who, space, body):
        with runtime_transaction(runtime, usuario_id=who, espacio_id=space) as session:
            return create_account(session, who, space, body)
    def denied(action, code):
        try: action()
        except HTTPException as e: assert e.status_code == code
        else: raise AssertionError('Operacion no autorizada aceptada')
    try:
        for user in users:
            with runtime_transaction(runtime, usuario_id=user) as s:
                s.execute(text('SELECT public.crear_espacio_personal()'))
        with migrator.begin() as c:
            c.execute(text("INSERT INTO public.miembros_espacio VALUES (:u,:s,'lector')"), {'u':reader,'s':owner})
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(lambda _: create(owner, owner, account), range(2)))
            assert rows[0] == rows[1] and rows[0]['nombre'] == 'Efectivo'
        denied(lambda: create(owner, owner, AccountInput(id=account.id,nombre='Otro')), 409)
        denied(lambda: create(other, owner, AccountInput(id=uuid4(),nombre='Ajeno')), 403)
        denied(lambda: create(reader, owner, AccountInput(id=uuid4(),nombre='Sin permiso')), 403)
        # Colision con ID ajeno no filtra nombre ni permite apropiarse de la cuenta.
        denied(lambda: create(other, other, account), 409)
        with runtime_transaction(runtime, usuario_id=reader, espacio_id=owner) as s:
            assert len(list_accounts(s, reader, owner)['items']) == 1
        with runtime_transaction(runtime, usuario_id=other, espacio_id=other) as s:
            assert list_accounts(s, other, other)['items'] == []
        with migrator.begin() as c:
            c.execute(text("INSERT INTO public.cuentas(id,espacio_id,nombre) VALUES (:id,:s,'Banco')"),
                      [{'id':uuid4(),'s':owner} for _ in range(100)])
        with runtime_transaction(runtime, usuario_id=owner, espacio_id=owner) as s:
            page = list_accounts(s, owner, owner)
            following = list_accounts(s, owner, owner, page['next_offset'])
            assert len(page['items']) == 100 and len(following['items']) == 1 and following['next_offset'] is None
            assert len({row['id'] for row in page['items'] + following['items']}) == 101
        print('OK: cuentas API, reintento concurrente, roles, aislamiento y paginacion.', flush=True)
    finally:
        with migrator.begin() as c:
            for user in users:
                c.execute(text('DELETE FROM public.cuentas WHERE espacio_id=:u'), {'u':user})
            for user in users:
                c.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u OR espacio_id=:u'), {'u':user})
            for user in users:
                c.execute(text('DELETE FROM public.espacios WHERE id=:u'), {'u':user})
                c.execute(text('DELETE FROM public.perfiles WHERE usuario_id=:u'), {'u':user})
        runtime.dispose(); migrator.dispose()
