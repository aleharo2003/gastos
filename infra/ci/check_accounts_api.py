"""Contrato de cuentas contra PostgreSQL real en la fixture de CI."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.accounts import AccountInput, AccountRename, create_account, list_accounts, rename_account, set_account_state
from app.expenses import ExpenseInput, create_expense, void_expense
from app.incomes import account_balance, savings_summary
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
    def rename(who, space, previous, new):
        body = AccountRename(nombre_anterior=previous, nombre=new)
        with runtime_transaction(runtime, usuario_id=who, espacio_id=space) as session:
            return rename_account(session, who, space, account.id, body)
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
        renamed = rename(owner, owner, 'Efectivo', 'Caja')
        assert renamed['id'] == account.id and renamed['nombre'] == 'Caja'
        assert rename(owner, owner, 'Efectivo', 'Caja') == renamed
        denied(lambda: rename(owner, owner, 'Efectivo', 'Otro'), 409)
        denied(lambda: rename(reader, owner, 'Caja', 'Otro'), 403)
        denied(lambda: rename(other, other, 'Caja', 'Otro'), 404)
        # Colision con ID ajeno no filtra nombre ni permite apropiarse de la cuenta.
        denied(lambda: create(other, other, account), 409)
        expense = ExpenseInput(id=uuid4(), fecha=date.today().isoformat(), descripcion='Compra',
                               moneda='ARS', importe='10.00')
        with runtime_transaction(runtime, usuario_id=owner, espacio_id=owner) as s:
            original = create_expense(s, owner, owner, account.id, expense)
            assert set_account_state(s, owner, owner, account.id, False)['activa'] is False
        with runtime_transaction(runtime, usuario_id=reader, espacio_id=owner) as s:
            assert list_accounts(s, reader, owner)['items'] == []
            assert list_accounts(s, reader, owner, inactive=True)['items'][0]['id'] == account.id
        with runtime_transaction(runtime, usuario_id=owner, espacio_id=owner) as s:
            assert create_expense(s, owner, owner, account.id, expense) == original
        try:
            with runtime_transaction(runtime, usuario_id=owner, espacio_id=owner) as s:
                create_expense(s, owner, owner, account.id, expense.model_copy(update={'id': uuid4()}))
        except IntegrityError as error:
            assert error.orig.diag.constraint_name == 'cuenta_activa_para_movimientos'
        else:
            raise AssertionError('La cuenta inactiva aceptó un nuevo gasto')
        with runtime_transaction(runtime, usuario_id=owner, espacio_id=owner) as s:
            assert set_account_state(s, owner, owner, account.id, True)['activa'] is True
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
        opening = AccountInput(id=uuid4(), nombre='Apertura USD', tipo='efectivo',
                               moneda='USD', saldo_inicial='250.25')
        row = create(owner, owner, opening)
        assert row['saldo_inicial'] == '250.25' and row['moneda'] == 'USD'
        assert create(owner, owner, opening) == row
        denied(lambda: create(owner, owner, AccountInput(
            id=opening.id, nombre='Apertura USD', tipo='efectivo', moneda='ARS',
            saldo_inicial='250.25',
        )), 409)
        paid = ExpenseInput(id=uuid4(), fecha=date.today().isoformat(), descripcion='Compra USD',
                            moneda='USD', importe='0.10')
        with runtime_transaction(runtime, usuario_id=owner, espacio_id=owner) as s:
            by_currency = lambda rows: {item['moneda']: item for item in rows}
            start = by_currency(account_balance(s, owner, owner, opening.id)['totales'])['USD']
            assert start['ingresos'] == '0.00' and start['saldo'] == '250.25'
            create_expense(s, owner, owner, opening.id, paid)
            assert by_currency(account_balance(s, owner, owner, opening.id)['totales'])['USD']['saldo'] == '250.15'
            month = date.today().isoformat()[:7]
            report = savings_summary(s, owner, owner, month, date.today())
            assert by_currency(report['saldo_total'])['USD']['total'] == '250.15'
            saved = next(item for item in report['cuentas'] if item['id'] == str(opening.id))
            assert by_currency(saved['saldos'])['USD']['total'] == '250.15'
            assert not any(item['moneda'] == 'USD' for item in report['ingresos'])
            void_expense(s, owner, owner, opening.id, paid.id)
            assert by_currency(account_balance(s, owner, owner, opening.id)['totales'])['USD']['saldo'] == '250.25'
        print('OK: cuentas API, reintento concurrente, roles, aislamiento y paginacion.', flush=True)
    finally:
        with migrator.begin() as c:
            for user in users:
                c.execute(text('DELETE FROM public.gastos WHERE espacio_id=:u'), {'u':user})
                c.execute(text('DELETE FROM public.cuentas WHERE espacio_id=:u'), {'u':user})
            for user in users:
                c.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u OR espacio_id=:u'), {'u':user})
            for user in users:
                c.execute(text('DELETE FROM public.espacios WHERE id=:u'), {'u':user})
                c.execute(text('DELETE FROM public.perfiles WHERE usuario_id=:u'), {'u':user})
        runtime.dispose(); migrator.dispose()
