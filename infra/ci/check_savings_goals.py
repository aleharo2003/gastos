"""Metas con saldos reales, concurrencia, aislamiento y archivo en PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from app.accounts import AccountInput,create_account
from app.incomes import IncomeInput,create_income,account_balance
from app.expenses import ExpenseInput,create_expense
from app.transfers import TransferInput,create_transfer
from app.savings_goals import GoalInput,GoalEdit,create_goal,edit_goal,list_goals
from app.db.connection import create_runtime_engine,create_migration_engine
from app.db.unit_of_work import runtime_transaction


def check_savings_goals(runtime_url,migration_url):
    runtime,migrator=create_runtime_engine(runtime_url),create_migration_engine(migration_url)
    owner,other,reader,editor=users=[uuid4() for _ in range(4)]
    bank,savings,empty,foreign=[uuid4() for _ in range(4)]

    def transaction(action,who=owner,space=owner):
        with runtime_transaction(runtime,usuario_id=who,espacio_id=space) as s:return action(s,who,space)

    def payload(**changes):
        return GoalInput(**(dict(id=uuid4(),cuenta_id=savings,nombre='Vacaciones',moneda='ARS',
            objetivo='100.00',fecha_objetivo='2027-01-01')|changes))

    def create(body,who=owner,space=owner):
        return transaction(lambda s,u,w:create_goal(s,u,w,body),who,space)

    def edit(goal,version,**changes):
        body=GoalEdit(**(dict(nombre=goal['nombre'],objetivo=goal['objetivo'],fecha_objetivo=goal['fecha_objetivo'],
                            archivada=goal['archivada'],version=version)|changes))
        return transaction(lambda s,u,w:edit_goal(s,u,w,goal['id'],body))

    def listed(archived=False,offset=0,who=owner):
        return transaction(lambda s,u,w:list_goals(s,u,w,offset,archived),who)

    def current(goal):
        return next(row for row in listed(True)['items'] if row['id']==goal['id'])

    def total():
        return transaction(lambda s,u,w:account_balance(s,u,w))

    def denied(action,code):
        try:action()
        except HTTPException as e:assert e.status_code==code
        else:raise AssertionError('Operacion no autorizada aceptada')

    def sql_denied(who,statement,params,code):
        try:transaction(lambda s,u,w:s.execute(text(statement),params),who)
        except DBAPIError as e:assert e.orig.sqlstate==code
        else:raise AssertionError('SQL no autorizado aceptado')

    def transfer(amount,reverse=False):
        body=TransferInput(id=uuid4(),origen_id=savings if reverse else bank,destino_id=bank if reverse else savings,
            fecha='2026-11-17',descripcion='Ahorro',moneda='ARS',importe=amount)
        transaction(lambda s,u,w:create_transfer(s,u,w,body))

    def expense(amount):
        body=ExpenseInput(id=uuid4(),fecha='2026-11-17',descripcion='Compra',moneda='ARS',importe=amount)
        transaction(lambda s,u,w:create_expense(s,u,w,savings,body))

    try:
        for user in users:
            with runtime_transaction(runtime,usuario_id=user) as s:s.execute(text('SELECT public.crear_espacio_personal()'))
        for user,account in [(owner,bank),(owner,savings),(owner,empty),(other,foreign)]:
            transaction(lambda s,u,w:create_account(s,u,w,AccountInput(id=account,nombre='Cuenta')),user,user)
        with migrator.begin() as c:
            c.execute(text('INSERT INTO public.miembros_espacio VALUES (:u,:s,:r)'),
                [{'u':reader,'s':owner,'r':'lector'},{'u':editor,'s':owner,'r':'editor'}])
        before=total();body=payload()
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(lambda _:create(body),range(2)))
        goal=rows[0];assert rows[0]==rows[1] and total()==before
        assert goal['acumulado']=='0.00' and goal['faltante']=='100.00'
        denied(lambda:create(payload()),409)
        denied(lambda:create(payload(cuenta_id=foreign)),404)
        denied(lambda:create(payload(cuenta_id=bank),reader),403)
        denied(lambda:create(payload(cuenta_id=bank),other),403)
        create(payload(cuenta_id=foreign),other,other)
        denied(lambda:listed(who=other),403)

        income=IncomeInput(id=uuid4(),fecha='2026-11-17',descripcion='Sueldo',moneda='ARS',importe='500')
        transaction(lambda s,u,w:create_income(s,u,w,bank,income))
        for _ in range(101):transfer('0.10')
        assert current(goal)['acumulado']=='10.10' and current(goal)['porcentaje']=='10.1'
        usd=create(payload(moneda='USD',objetivo='10.00'),editor)
        income_usd=IncomeInput(id=uuid4(),fecha='2026-11-17',descripcion='Regalo',moneda='USD',importe='20')
        transaction(lambda s,u,w:create_income(s,u,w,savings,income_usd))
        assert current(usd)['alcanzada'] and current(usd)['porcentaje']=='100.0'
        assert current(goal)['acumulado']=='10.10'
        expense('5');transfer('1',True)
        assert current(goal)['acumulado']=='4.10'
        expense('10')
        assert current(goal)['saldo']=='-5.90' and current(goal)['acumulado']=='0.00' and current(goal)['porcentaje']=='0.0'
        transfer('105.90')
        assert current(goal)['acumulado']=='100.00' and current(goal)['alcanzada']
        before=total()
        raised=edit(goal,0,objetivo='200.00')
        assert raised['porcentaje']=='50.0' and total()==before
        assert edit(goal,0,objetivo='200.00')['version']==1
        denied(lambda:edit(goal,0,nombre='Cambio viejo'),409)
        archived=edit(raised,1,archivada=True)
        assert len(listed()['items'])==1
        replacement=create(payload(nombre='Casa'))
        all_rows=listed(True)['items']
        assert [r['saldo'] for r in all_rows if r['cuenta_id']==str(savings) and r['moneda']=='ARS']==['100.00','100.00']
        denied(lambda:edit(archived,2,archivada=False),409)
        assert current(archived)['archivada'] and current(archived)['version']==2
        edit(replacement,0,archivada=True)
        active=edit(archived,2,archivada=False)
        assert active['version']==3 and total()==before
        # Dos metas diferentes compiten por la misma cuenta/moneda: solo una queda activa.
        candidates=[payload(cuenta_id=empty),payload(cuenta_id=empty)]
        def competing_create(item):
            try:return create(item)
            except HTTPException as e:assert e.status_code==409;return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(competing_create,candidates))
        assert sum(row is not None for row in results)==1
        def competing_edit(name):
            try:return edit(active,3,nombre=name)
            except HTTPException as e:assert e.status_code==409;return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(competing_edit,['Viaje A','Viaje B']))
        assert sum(row is not None for row in results)==1

        # Paginar metas archivadas no multiplica los saldos de cuentas repetidas.
        insert="""INSERT INTO public.metas_ahorro
            (id,espacio_id,cuenta_id,usuario_id,nombre,moneda,objetivo,fecha_objetivo,archivada,version)
            VALUES (:id,:s,:a,:u,'Archivo','ARS',100,NULL,:archived,0)"""
        params={'id':uuid4(),'s':owner,'a':savings,'u':owner,'archived':True}
        with migrator.begin() as c:c.execute(text(insert),[params|{'id':uuid4()} for _ in range(101)])
        first=listed(True);second=listed(True,first['next_offset'])
        assert len(first['items'])==100 and len(second['items'])==5 and second['next_offset'] is None
        assert len({r['id'] for r in first['items']+second['items']})==105
        assert all(r['saldo']=='100.00' for r in first['items']+second['items'] if r['cuenta_id']==str(savings) and r['moneda']=='ARS')
        assert listed(who=reader)==listed()
        sql_denied(owner,insert,params|{'u':other},'42501')
        sql_denied(reader,insert,params|{'u':reader},'42501')
        sql_denied(owner,'UPDATE public.metas_ahorro SET cuenta_id=:id',{'id':foreign},'42501')
        sql_denied(owner,'DELETE FROM public.metas_ahorro',{},'42501')
        with runtime.begin() as c:assert c.execute(text('SELECT count(*) FROM public.metas_ahorro')).scalar_one()==0
        assert transaction(lambda s,u,w:s.execute(text("UPDATE public.metas_ahorro SET nombre='No'")).rowcount,reader)==0
        try:
            with migrator.begin() as c:c.execute(text(insert),params|{'a':foreign})
        except DBAPIError as e:assert e.orig.sqlstate=='23503'
        else:raise AssertionError('FK cruzada aceptada')
        denied(lambda:transaction(lambda s,u,w:edit_goal(s,u,w,goal['id'],GoalEdit(nombre='No',objetivo='100',version=4,archivada=False)),reader),403)
        with migrator.begin() as c:c.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u AND espacio_id=:s'),{'u':editor,'s':owner})
        denied(lambda:create(payload(cuenta_id=bank),editor),403)
        print('OK: metas, saldos reales >100 transferencias, retiros, gastos, monedas, archivo, unicidad concurrente, edicion versionada, RLS y paginacion sin duplicar.',flush=True)
    finally:
        with migrator.begin() as c:
            for table in ['metas_ahorro','transferencias','ingresos','gastos','cuentas']:
                for user in users:c.execute(text(f'DELETE FROM public.{table} WHERE espacio_id=:u'),{'u':user})
            for user in users:c.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u OR espacio_id=:u'),{'u':user})
            for user in users:
                c.execute(text('DELETE FROM public.espacios WHERE id=:u'),{'u':user})
                c.execute(text('DELETE FROM public.perfiles WHERE usuario_id=:u'),{'u':user})
        runtime.dispose();migrator.dispose()
