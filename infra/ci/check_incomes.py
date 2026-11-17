"""Ingresos y saldos sobre PostgreSQL desechable, con el rol runtime real."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from app.accounts import AccountInput, create_account
from app.incomes import IncomeInput, create_income, list_incomes, account_balance
from app.expenses import ExpenseInput, ExpenseEdit, create_expense, edit_expense
from app.db.connection import create_runtime_engine, create_migration_engine
from app.db.unit_of_work import runtime_transaction


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
        assert totals()['ARS']==dict(moneda='ARS',ingresos='100.10',gastos='150.20',saldo='-50.10')
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

        insert="""INSERT INTO public.ingresos(id,espacio_id,cuenta_id,usuario_id,fecha,descripcion,moneda,importe)
            VALUES (:id,:s,:a,:u,'2026-11-16','SQL','ARS',1)"""
        params={'id':uuid4(),'s':owner,'a':account,'u':other}
        sql_denied(owner,insert,params,'42501')
        sql_denied(reader,insert,params | {'u':reader},'42501')
        sql_denied(owner,'DELETE FROM public.ingresos',{},'42501')
        sql_denied(owner,'UPDATE public.ingresos SET importe=1',{},'42501')
        with runtime_transaction(runtime) as session:
            assert session.execute(text('SELECT count(*) FROM public.ingresos')).scalar_one()==0
        with runtime_transaction(runtime,usuario_id=other,espacio_id=other) as session:
            assert session.execute(text('SELECT count(*) FROM public.ingresos WHERE espacio_id=:s'),{'s':owner}).scalar_one()==0
        try:
            with migrator.begin() as c: c.execute(text(insert),params | {'a':foreign})
        except DBAPIError as error: assert error.orig.sqlstate=='23503'
        else: raise AssertionError('Se acepto ingreso en cuenta de otro espacio')
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
