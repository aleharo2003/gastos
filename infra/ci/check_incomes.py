"""Ingresos y saldos sobre PostgreSQL desechable, con el rol runtime real."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from app.accounts import AccountInput, create_account
from app.incomes import IncomeInput, create_income, list_incomes, account_balance, savings_summary
from app.expenses import ExpenseInput, ExpenseEdit, create_expense, edit_expense
from app.db.connection import create_runtime_engine, create_migration_engine
from app.db.unit_of_work import runtime_transaction
from app.movements import list_movements, parse_cursor, void_movement
from app.expense_import import ImportRequest, cancel_batch, import_rows, recent_batches


def check_incomes(runtime_url, migration_url):
    runtime = create_runtime_engine(runtime_url)
    migrator = create_migration_engine(migration_url)
    owner, other, reader, editor = users = [uuid4() for _ in range(4)]
    account, second, foreign = [uuid4() for _ in range(3)]

    def call(operation, who=owner, space=owner, acct=account, *args):
        with runtime_transaction(runtime, usuario_id=who, espacio_id=space) as session:
            return operation(session, who, space, acct, *args)

    def payload(**changes):
        return IncomeInput(**(dict(id=uuid4(), fecha='2026-11-16', descripcion='Sueldo',
                                   moneda='ARS', importe='100.10') | changes))

    def denied(action, code):
        try: action()
        except HTTPException as error: assert error.status_code == code
        else: raise AssertionError('Se acepto una operacion prohibida')

    def sql_denied(who, sql, params, code):
        try:
            with runtime_transaction(runtime, usuario_id=who, espacio_id=owner) as session:
                session.execute(text(sql), params)
        except DBAPIError as error: assert error.orig.sqlstate == code
        else: raise AssertionError('Se acepto SQL prohibido')

    try:
        for user in users:
            with runtime_transaction(runtime, usuario_id=user) as session:
                session.execute(text('SELECT public.crear_espacio_personal()'))
        for user, acct in [(owner, account), (owner, second), (other, foreign)]:
            call(lambda s,u,w,a:create_account(s,u,w,AccountInput(id=a,nombre='Banco')),user,user,acct)
        with migrator.begin() as c:
            c.execute(text('INSERT INTO public.miembros_espacio VALUES (:u,:s,:r)'),
                      [{'u':reader,'s':owner,'r':'lector'},{'u':editor,'s':owner,'r':'editor'}])

        def totals(acct=account, who=owner):
            return {r['moneda']:r for r in call(account_balance,who,owner,acct)['totales']}

        assert all(row['saldo']=='0.00' for row in totals().values())
        income = payload()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _:call(create_income,owner,owner,account,income),range(2)))
        assert results[0] == results[1]
        assert totals()['ARS']['saldo'] == '100.10'
        denied(lambda:call(create_income,owner,owner,account,payload(id=income.id,importe='101')),409)
        denied(lambda:call(create_income,reader,owner,account,payload()),403)
        denied(lambda:call(create_income,other,owner,account,payload()),403)
        denied(lambda:call(create_income,owner,owner,foreign,payload()),404)
        call(create_income,editor,owner,account,payload(moneda='USD',importe='0.10'))
        call(create_income,owner,owner,second,payload(importe='50'))
        call(create_income,other,other,foreign,payload(importe='999999999999.99'))
        expense=ExpenseInput(id=uuid4(),fecha='2026-11-16',descripcion='Compra',moneda='ARS',importe='150.20')
        call(create_expense,owner,owner,account,expense)
        assert totals()['ARS']==dict(moneda='ARS',ingresos='100.10',gastos='150.20',transferencias_entrada='0.00',transferencias_salida='0.00',saldo='-50.10')
        assert totals()['USD']['saldo']=='0.10'
        assert totals()['EUR']['saldo']=='0.00'
        assert totals(None)['ARS']['saldo']=='-0.10'
        assert totals(who=reader)==totals()
        denied(lambda:call(account_balance,other,owner,account),403)
        denied(lambda:call(account_balance,owner,owner,foreign),404)
        denied(lambda:call(list_incomes,other,owner,account),403)
        denied(lambda:call(list_incomes,owner,owner,foreign),404)

        changed=ExpenseInput(**(expense.model_dump(mode='json') | {'importe':'100.00'}))
        edit=ExpenseEdit(original=expense,nuevo=changed)
        call(lambda s,u,w,a:edit_expense(s,u,w,a,expense.id,edit),editor,owner,account)
        assert totals()['ARS']['saldo']=='0.10'

        # Mas de 100 filas: el saldo no se calcula con la pagina visible.
        for _ in range(101):
            call(create_income,owner,owner,account,payload(importe='0.10'))
        page=call(list_incomes,reader,owner,account)
        following=call(list_incomes,reader,owner,account,page['next_offset'])
        assert len(page['items'])==100 and len(following['items'])==3
        assert following['next_offset'] is None
        assert len({r['id'] for r in page['items']+following['items']})==103
        assert totals()['ARS']['saldo']=='10.20'
        assert totals(None)['ARS']['saldo']=='60.20'
        assert len(call(list_incomes,reader,owner,None)['items'])==100

        def report(who=reader, current=date(2026,11,30), month='2026-11'):
            with runtime_transaction(runtime, usuario_id=who, espacio_id=owner) as session:
                return savings_summary(session, who, owner, month, current)

        savings = report()
        assert {(r['concepto'], r['moneda'], r['total']) for r in savings['ingresos']} == {
            ('Sueldo', 'ARS', '160.20'), ('Sueldo', 'USD', '0.10'),
        }
        assert {(r['tipo'], r['moneda'], r['total']) for r in savings['actividad']} == {
            ('ingresos_anuales', 'ARS', '160.20'), ('ingresos_anuales', 'USD', '0.10'), ('otros_gastos', 'ARS', '100.00'),
        }
        assert {r['moneda']: r['total'] for r in savings['saldo_total']} == {
            'ARS': '60.20', 'USD': '0.10', 'EUR': '0.00',
        }
        assert {row['id'] for row in savings['cuentas']} == {str(account), str(second)}
        assert report(current=date(2026,11,15))['ingresos'] == []
        denied(lambda: report(who=other), 403)
        denied(lambda: report(month='2026-12'), 422)

        insert="""INSERT INTO public.ingresos(id,espacio_id,cuenta_id,usuario_id,fecha,descripcion,moneda,importe)
            VALUES (:id,:s,:a,:u,'2026-11-16','SQL','ARS',1)"""
        params={'id':uuid4(),'s':owner,'a':account,'u':other}
        sql_denied(owner,insert,params,'42501')
        sql_denied(reader,insert,params | {'u':reader},'42501')
        sql_denied(owner,'DELETE FROM public.ingresos',{},'42501')
        sql_denied(owner,'UPDATE public.ingresos SET importe=1',{},'42501')
        with runtime.begin() as session:
            assert session.execute(text('SELECT count(*) FROM public.ingresos')).scalar_one()==0
        with runtime_transaction(runtime,usuario_id=other,espacio_id=other) as session:
            assert session.execute(text('SELECT count(*) FROM public.ingresos WHERE espacio_id=:s'),{'s':owner}).scalar_one()==0
        try:
            with migrator.begin() as c: c.execute(text(insert),params | {'a':foreign})
        except DBAPIError as error: assert error.orig.sqlstate=='23503'
        else: raise AssertionError('Se acepto ingreso en cuenta de otro espacio')
        categorized = payload(fecha='2026-11-17', descripcion='Ingreso categorizado', categoria='sueldo')
        assert call(create_income, owner, owner, account, categorized)['categoria'] == 'sueldo'
        assert call(create_income, owner, owner, account, categorized)['id'] == str(categorized.id)
        denied(lambda: call(create_income, owner, owner, account, payload(categoria='alimentos')), 422)
        denied(lambda: call(create_income, owner, owner, account, payload(id=categorized.id, categoria='honorarios')), 409)
        assert call(list_incomes, reader, owner, account)['items'][0]['categoria'] == 'sueldo'
        with runtime_transaction(runtime, usuario_id=reader, espacio_id=owner) as session:
            filters = dict(desde=None, hasta=None, tipo='ingreso', moneda='ARS', cuenta=account, texto='Ingreso categorizado')
            history = list_movements(session, reader, owner, filters | {'categoria_ingreso': 'sueldo'}, None)
            assert not list_movements(session, reader, owner, filters | {'categoria_ingreso': 'sin_categoria'}, None)['items']
            all_filters = filters | {'texto': ''}
            first = list_movements(session, reader, owner, all_filters, None)
            second = list_movements(session, reader, owner, all_filters, parse_cursor(first['next_cursor']))
            third = list_movements(session, reader, owner, all_filters, parse_cursor(second['next_cursor']))
            ids = [row['id'] for page in (first, second, third) for row in page['items']]
            assert len(ids) > 100 and len(ids) == len(set(ids))
            assert first['totales'] == second['totales'] == third['totales']
        assert [(row['id'], row['categoria']) for row in history['items']] == [(str(categorized.id), 'sueldo')]

        row = dict(fecha='2026-11-17', descripcion='Ingreso categorizado', moneda='ARS', importe='100.10')
        request = ImportRequest(filas=[row, row])
        before_import = totals()['ARS']['saldo']
        with runtime_transaction(runtime, usuario_id=owner, espacio_id=owner) as session:
            preview = import_rows(session, owner, owner, account, request, commit=False, kind='ingreso')
            assert preview['nuevas'] == 1 and preview['coincidencias_manuales'] == [0]
            batch = uuid4()
            confirmed = request.model_copy(update={'lote': batch, 'revision': preview['revision']})
            assert import_rows(session, owner, owner, account, confirmed, commit=True, kind='ingreso')['importadas'] == 1
            assert import_rows(session, owner, owner, account, confirmed, commit=True, kind='ingreso')['importadas'] == 1
        assert totals()['ARS']['saldo'] == str(Decimal(before_import) + Decimal('100.10'))
        with runtime_transaction(runtime, usuario_id=owner, espacio_id=owner) as session:
            assert import_rows(session, owner, owner, account, request, commit=False, kind='ingreso')['duplicadas'] == [1]
            assert recent_batches(session, owner, owner, account, 'ingreso')['items'][0]['lote'] == batch
            assert cancel_batch(session, owner, owner, account, batch) == {'anuladas': 0}
            assert cancel_batch(session, owner, owner, account, batch, 'ingreso') == {'anuladas': 1}
            assert cancel_batch(session, owner, owner, account, batch, 'ingreso') == {'anuladas': 0}
            audited = list_movements(session, owner, owner, filters | {'anulados': True}, None)
            assert len(audited['items']) == 1 and audited['items'][0]['anulado']
        assert totals()['ARS']['saldo'] == before_import
        assert call(list_incomes, reader, owner, account)['items'][0]['id'] == str(categorized.id)

        manual = payload(descripcion='Ingreso manual a anular', importe='17.00')
        before = totals()['ARS']['saldo']
        call(create_income, owner, owner, account, manual)

        def void(who, space=owner, identifier=manual.id):
            with runtime_transaction(runtime, usuario_id=who, espacio_id=space) as session:
                return void_movement(session, who, space, 'ingreso', identifier)

        denied(lambda: void(reader), 403)
        denied(lambda: void(other), 403)
        denied(lambda: void(other, other), 404)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda who: void(who), (owner, editor)))
        assert results == [{'id': str(manual.id), 'anulado': True}] * 2
        assert totals()['ARS']['saldo'] == before
        assert all(row['concepto'] != manual.descripcion for row in report()['ingresos'])
        with runtime_transaction(runtime, usuario_id=owner, espacio_id=owner) as session:
            search = dict(desde=None, hasta=None, tipo='ingreso', moneda=None, cuenta=account, texto=manual.descripcion)
            assert list_movements(session, owner, owner, search, None)['items'] == []
            audit = list_movements(session, owner, owner, search | {'anulados': True}, None)
            assert [(row['id'], row['anulado']) for row in audit['items']] == [(str(manual.id), True)]
            assert audit['totales'] == []

        with migrator.begin() as c:
            c.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u AND espacio_id=:s'),{'u':editor,'s':owner})
        denied(lambda:call(create_income,editor,owner,account,payload()),403)
        print('OK: ingresos concurrentes sin duplicar, saldos exactos >100 filas, edicion de gastos, monedas, roles y aislamiento SQL.',flush=True)
    finally:
        with migrator.begin() as c:
            for table in ['ingresos','gastos','cuentas']:
                for user in users: c.execute(text(f'DELETE FROM public.{table} WHERE espacio_id=:u'),{'u':user})
            for user in users: c.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u OR espacio_id=:u'),{'u':user})
            for user in users:
                c.execute(text('DELETE FROM public.espacios WHERE id=:u'),{'u':user})
                c.execute(text('DELETE FROM public.perfiles WHERE usuario_id=:u'),{'u':user})
        runtime.dispose()
        migrator.dispose()
