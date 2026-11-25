"""Transferencias reales: atomicidad, conservacion, RLS y reintentos."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from app.accounts import AccountInput,create_account
from app.transfers import TransferInput,create_transfer,list_transfers
from app.incomes import IncomeInput,create_income,account_balance
from app.movements import list_movements, parse_cursor
from app.expenses import ExpenseInput,create_expense,expense_summary
from app.db.connection import create_runtime_engine,create_migration_engine
from app.db.unit_of_work import runtime_transaction


def check_transfers(runtime_url,migration_url):
    runtime,migrator=create_runtime_engine(runtime_url),create_migration_engine(migration_url)
    owner,other,reader,editor=users=[uuid4() for _ in range(4)]
    source,savings,empty,foreign,foreign_target=[uuid4() for _ in range(5)]

    def transfer(who,space,payload):
        with runtime_transaction(runtime,usuario_id=who,espacio_id=space) as session:
            return create_transfer(session,who,space,payload)

    def body(**changes):
        return TransferInput(**(dict(id=uuid4(),origen_id=source,destino_id=savings,
            fecha='2026-11-17',descripcion='Ahorro',moneda='ARS',importe='100.10')|changes))

    def balance(account=None,who=owner):
        with runtime_transaction(runtime,usuario_id=who,espacio_id=owner) as session:
            return {row['moneda']:row for row in account_balance(session,who,owner,account)['totales']}

    def page(account=None,offset=0,who=owner):
        with runtime_transaction(runtime,usuario_id=who,espacio_id=owner) as session:
            return list_transfers(session,who,owner,account,offset)

    def denied(action,code):
        try: action()
        except HTTPException as error: assert error.status_code==code
        else: raise AssertionError('Operacion prohibida aceptada')

    def sql_denied(who,statement,params,code):
        try:
            with runtime_transaction(runtime,usuario_id=who,espacio_id=owner) as session:
                session.execute(text(statement),params)
        except DBAPIError as error: assert error.orig.sqlstate==code
        else: raise AssertionError('SQL prohibido aceptado')

    try:
        for user in users:
            with runtime_transaction(runtime,usuario_id=user) as session:
                session.execute(text('SELECT public.crear_espacio_personal()'))
        for user,account in [(owner,source),(owner,savings),(owner,empty),(other,foreign),(other,foreign_target)]:
            with runtime_transaction(runtime,usuario_id=user,espacio_id=user) as session:
                create_account(session,user,user,AccountInput(id=account,nombre='Cuenta'))
        with migrator.begin() as c:
            c.execute(text('INSERT INTO public.miembros_espacio VALUES (:u,:s,:r)'),
                [{'u':reader,'s':owner,'r':'lector'},{'u':editor,'s':owner,'r':'editor'}])
        with runtime_transaction(runtime,usuario_id=owner,espacio_id=owner) as session:
            create_income(session,owner,owner,source,IncomeInput(id=uuid4(),fecha='2026-11-17',descripcion='Sueldo',moneda='ARS',importe='500.00'))
            create_expense(session,owner,owner,source,ExpenseInput(id=uuid4(),fecha='2026-11-17',descripcion='Comida',moneda='ARS',importe='20.00'))
            before=expense_summary(session,owner,owner)
        payload=body()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:transfer(owner,owner,payload),range(2)))
        assert results[0]==results[1] and len(page()['items'])==1
        assert balance(source)['ARS']['saldo']=='379.90'
        assert balance(savings)['ARS']['saldo']=='100.10'
        assert balance()['ARS']['saldo']=='480.00'
        assert balance()['ARS']['ingresos']=='500.00' and balance()['ARS']['gastos']=='20.00'
        assert balance(savings)['ARS']['ingresos']=='0.00' and balance(source)['ARS']['gastos']=='20.00'
        assert balance(source)['ARS']['transferencias_salida']=='100.10'
        assert balance(savings)['ARS']['transferencias_entrada']=='100.10'
        assert balance(empty)['ARS']['saldo']=='0.00'
        assert balance(who=reader)==balance()
        denied(lambda:transfer(owner,owner,body(id=payload.id,importe='100.11')),409)
        denied(lambda:transfer(owner,owner,body(id=payload.id,destino_id=empty)),409)
        denied(lambda:transfer(reader,owner,body()),403)
        denied(lambda:transfer(other,owner,body()),403)
        denied(lambda:transfer(owner,owner,body(destino_id=foreign)),404)
        denied(lambda:transfer(owner,owner,body(origen_id=foreign)),404)
        denied(lambda:page(who=other),403)
        denied(lambda:page(account=foreign),404)
        assert len(page()['items'])==1

        # Una excepcion posterior al INSERT revierte ambos efectos.
        try:
            with runtime_transaction(runtime,usuario_id=owner,espacio_id=owner) as session:
                create_transfer(session,owner,owner,body(importe='7.00'))
                raise RuntimeError('rollback de prueba')
        except RuntimeError:
            pass
        assert len(page()['items'])==1 and balance()['ARS']['saldo']=='480.00'
        transfer(editor,owner,body(origen_id=savings,destino_id=source,importe='0.10'))
        assert balance(source)['ARS']['saldo']=='380.00' and balance(savings)['ARS']['saldo']=='100.00'
        for currency in ['USD','EUR']:
            transfer(owner,owner,body(moneda=currency,importe='0.10'))
            assert balance(source)[currency]['saldo']=='-0.10'
            assert balance(savings)[currency]['saldo']=='0.10'
            assert balance()[currency]['saldo']=='0.00'

        # El saldo no depende de los primeros 100 movimientos del historial.
        for _ in range(101): transfer(owner,owner,body(importe='0.10'))
        first=page(account=source,who=reader)
        second=page(account=source,offset=first['next_offset'],who=reader)
        assert len(first['items'])==100 and len(second['items'])==5 and second['next_offset'] is None
        assert len({row['id'] for row in first['items']+second['items']})==105
        assert balance(source)['ARS']['saldo']=='369.90' and balance(savings)['ARS']['saldo']=='110.10'
        assert balance()['ARS']['saldo']=='480.00'
        assert len(page(account=savings)['items'])==100 and not page(account=empty)['items']
        transfer(other,other,body(origen_id=foreign,destino_id=foreign_target,importe='999.00'))
        assert balance()['ARS']['saldo']=='480.00'
        assert len(page()['items'])==100 and page()['next_offset']==100
        filters = {'desde': None, 'hasta': None, 'tipo': None, 'moneda': 'ARS',
                   'cuenta': source, 'texto': ''}
        with runtime_transaction(runtime, usuario_id=reader, espacio_id=owner) as session:
            movement_page = list_movements(session, reader, owner, filters, None)
            following = list_movements(session, reader, owner, filters, parse_cursor(movement_page['next_cursor']))
            assert len(movement_page['items']) == len(following['items']) == 50
            assert not {row['id'] for row in movement_page['items']} & {row['id'] for row in following['items']}
            assert movement_page['totales'] == following['totales'] == [
                {'moneda': 'ARS', 'ingresos': '500.00', 'gastos': '20.00', 'transferencias': '110.30', 'variacion_cuenta': '369.90'}]
            uncategorized = list_movements(session, reader, owner, filters | {'categoria': 'sin_categoria'}, None)
            assert [row['tipo'] for row in uncategorized['items']] == ['gasto']
            assert uncategorized['totales'][0]['gastos'] == '20.00'
            filtered = list_movements(session, reader, owner, filters | {'texto': 'sÚeLdO'}, None)
            assert [row['tipo'] for row in filtered['items']] == ['ingreso']
            assert filtered['items'][0]['destino'] == 'Cuenta'
        # Datos ajenos al espacio no afectan los agregados.
        with runtime_transaction(runtime,usuario_id=owner,espacio_id=owner) as session:
            assert expense_summary(session,owner,owner)==before

        insert="""INSERT INTO public.transferencias
            (id,espacio_id,origen_id,destino_id,usuario_id,fecha,descripcion,moneda,importe)
            VALUES (:id,:s,:o,:t,:u,'2026-11-17','SQL','ARS',1)"""
        params={'id':uuid4(),'s':owner,'o':source,'t':savings,'u':other}
        sql_denied(owner,insert,params,'42501')
        sql_denied(reader,insert,params|{'u':reader},'42501')
        sql_denied(owner,'DELETE FROM public.transferencias',{},'42501')
        sql_denied(owner,'UPDATE public.transferencias SET importe=1',{},'42501')
        with runtime.begin() as c:
            assert c.execute(text('SELECT count(*) FROM public.transferencias')).scalar_one()==0
        with runtime_transaction(runtime,usuario_id=other,espacio_id=other) as session:
            assert session.execute(text('SELECT count(*) FROM public.transferencias WHERE espacio_id=:s'),{'s':owner}).scalar_one()==0
        for changed,code in [({'o':foreign},'23503'),({'t':foreign},'23503'),({'t':source},'23514')]:
            try:
                with migrator.begin() as c: c.execute(text(insert),params|changed)
            except DBAPIError as error: assert error.orig.sqlstate==code
            else: raise AssertionError('Restriccion de cuentas omitida')
        with migrator.begin() as c:
            c.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u AND espacio_id=:s'),{'u':editor,'s':owner})
        denied(lambda:transfer(editor,owner,body()),403)
        print('OK: transferencias atomicas, conservacion por moneda, retiro de ahorros, >100 filas, concurrencia, rollback, roles y ambas FK.',flush=True)
    finally:
        with migrator.begin() as c:
            for table in ['transferencias','ingresos','gastos','cuentas']:
                for user in users:c.execute(text(f'DELETE FROM public.{table} WHERE espacio_id=:u'),{'u':user})
            for user in users:c.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u OR espacio_id=:u'),{'u':user})
            for user in users:
                c.execute(text('DELETE FROM public.espacios WHERE id=:u'),{'u':user})
                c.execute(text('DELETE FROM public.perfiles WHERE usuario_id=:u'),{'u':user})
        runtime.dispose();migrator.dispose()
