"""Gastos: dinero exacto, aislamiento y reintento contra la base desechable."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from app.accounts import AccountInput, create_account
from app.expenses import ExpenseInput, create_expense, list_expenses
from app.db.connection import create_runtime_engine, create_migration_engine
from app.db.unit_of_work import runtime_transaction


def check_expenses_api(runtime_url, migration_url):
    runtime,migrator=create_runtime_engine(runtime_url),create_migration_engine(migration_url)
    owner,other,reader,editor=[uuid4() for _ in range(4)];users=[owner,other,reader,editor]
    account,foreign=uuid4(),uuid4()
    def body(**kw):
        return ExpenseInput(**(dict(id=uuid4(),fecha='2026-11-06',descripcion='Comida',moneda='ARS',importe='0.10')|kw))
    def create(who,space,acct,payload):
        with runtime_transaction(runtime,usuario_id=who,espacio_id=space) as s:
            return create_expense(s,who,space,acct,payload)
    def denied(action,code):
        try: action()
        except HTTPException as e: assert e.status_code==code
        else: raise AssertionError('Se acepto acceso no permitido')
    def sql_denied(who,sql,params,code):
        try:
            with runtime_transaction(runtime,usuario_id=who,espacio_id=owner) as s: s.execute(text(sql),params)
        except DBAPIError as e: assert e.orig.sqlstate==code
        else: raise AssertionError('SQL no autorizado aceptado')
    try:
        for user in users:
            with runtime_transaction(runtime,usuario_id=user) as s: s.execute(text('SELECT public.crear_espacio_personal()'))
        for user,acct in [(owner,account),(other,foreign)]:
            with runtime_transaction(runtime,usuario_id=user,espacio_id=user) as s:
                create_account(s,user,user,AccountInput(id=acct,nombre='Banco'))
        with migrator.begin() as c:
            c.execute(text('INSERT INTO public.miembros_espacio VALUES (:u,:s,:r)'),[{'u':reader,'s':owner,'r':'lector'},{'u':editor,'s':owner,'r':'editor'}])
        payload=body()
        with ThreadPoolExecutor(max_workers=2) as pool: rows=list(pool.map(lambda _:create(owner,owner,account,payload),range(2)))
        assert rows[0]==rows[1] and rows[0]['importe']=='0.10'
        create(editor,owner,account,body(moneda='USD',importe='999999999999.99'))
        create(owner,owner,account,body(moneda='EUR',importe='12.50'))
        denied(lambda:create(owner,owner,account,body(id=payload.id,importe='0.11')),409)
        denied(lambda:create(reader,owner,account,body()),403)
        denied(lambda:create(other,owner,account,body()),403)
        denied(lambda:create(owner,owner,foreign,body()),404)
        with runtime_transaction(runtime,usuario_id=reader,espacio_id=owner) as s:
            page=list_expenses(s,reader,owner,account)
            assert {r['moneda'] for r in page['items']}=={'ARS','USD','EUR'}
            assert len(page['items'])==3
        insert="INSERT INTO public.gastos VALUES (:id,:s,:a,:u,'2026-11-06','SQL','ARS',1)"
        params={'id':uuid4(),'s':owner,'a':account,'u':other}
        sql_denied(owner,insert,params,'42501')
        sql_denied(reader,insert,params|{'u':reader},'42501')
        sql_denied(owner,'DELETE FROM public.gastos',{},'42501')
        sql_denied(owner,"UPDATE public.gastos SET importe=2",{},'42501')
        # La FK compuesta protege incluso cuando el migrador no esta sujeto a la policy runtime.
        try:
            with migrator.begin() as c: c.execute(text(insert),params|{'a':foreign})
        except DBAPIError as e: assert e.orig.sqlstate=='23503'
        else: raise AssertionError('Enlace a cuenta de otro espacio aceptado')
        with migrator.begin() as c:
            c.execute(text(insert),[params|{'id':uuid4(),'u':owner} for _ in range(98)])
        with runtime_transaction(runtime,usuario_id=owner,espacio_id=owner) as s:
            page=list_expenses(s,owner,owner,account);following=list_expenses(s,owner,owner,account,page['next_offset'])
            assert len(page['items'])==100 and len(following['items'])==1
            assert len({r['id'] for r in page['items']+following['items']})==101
        with migrator.begin() as c: c.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u AND espacio_id=:s'),{'u':editor,'s':owner})
        denied(lambda:create(editor,owner,account,body()),403)
        print('OK: gastos multimoneda, precision, reintentos, roles, FK por espacio y paginacion.',flush=True)
    finally:
        with migrator.begin() as c:
            for table in ['gastos','cuentas']:
                for user in users: c.execute(text(f'DELETE FROM public.{table} WHERE espacio_id=:u'),{'u':user})
            for user in users: c.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u OR espacio_id=:u'),{'u':user})
            for user in users:
                c.execute(text('DELETE FROM public.espacios WHERE id=:u'),{'u':user})
                c.execute(text('DELETE FROM public.perfiles WHERE usuario_id=:u'),{'u':user})
        runtime.dispose();migrator.dispose()
