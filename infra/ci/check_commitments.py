"""Deudas fijas y pagos reales contra PostgreSQL desechable."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from app.accounts import AccountInput,create_account
from app.incomes import IncomeInput,create_income,account_balance
from app.expenses import ExpenseInput,ExpenseEdit,create_expense,edit_expense
from app.commitments import CommitmentInput,PaymentInput,create_commitment,list_commitments,list_installments,pay_installment,list_payments,monthly_installments
from app.db.connection import create_runtime_engine,create_migration_engine
from app.db.unit_of_work import runtime_transaction


def check_commitments(runtime_url,migration_url):
    runtime,migrator=create_runtime_engine(runtime_url),create_migration_engine(migration_url)
    owner,other,reader,editor=users=[uuid4() for _ in range(4)]
    bank,second,foreign=[uuid4() for _ in range(3)]
    def call(action,who=owner,space=owner):
        with runtime_transaction(runtime,usuario_id=who,espacio_id=space) as s:return action(s,who,space)
    def body(**changes):
        return CommitmentInput(**(dict(id=uuid4(),cuenta_id=bank,nombre='Deuda',moneda='ARS',importe='100',
            categoria=None,primer_vencimiento='2024-01-31',total_cuotas=3)|changes))
    def payment(**changes):
        return PaymentInput(**(dict(id=uuid4(),cuenta_id=bank,fecha='2026-11-17',importe='30')|changes))
    def create(payload,who=owner,space=owner):return call(lambda s,u,w:create_commitment(s,u,w,payload),who,space)
    def cuotas(commitment,offset=0,who=owner,space=owner):return call(lambda s,u,w:list_installments(s,u,w,commitment,offset),who,space)
    def pay(identifier,payload,who=owner,space=owner):return call(lambda s,u,w:pay_installment(s,u,w,identifier,payload),who,space)
    def balance():return call(lambda s,u,w:account_balance(s,u,w,bank))['totales'][0]['saldo']
    def listed():return call(lambda s,u,w:list_commitments(s,u,w))['items']
    def denied(action,code):
        try:action()
        except HTTPException as e:assert e.status_code==code
        else:raise AssertionError('Operacion prohibida aceptada')
    def sql_denied(action,code):
        try:action()
        except DBAPIError as e:assert e.orig.sqlstate==code
        else:raise AssertionError('SQL prohibido aceptado')
    try:
        for user in users:
            with runtime_transaction(runtime,usuario_id=user) as s:s.execute(text('SELECT public.crear_espacio_personal()'))
        for user,account in [(owner,bank),(owner,second),(other,foreign)]:
            call(lambda s,u,w:create_account(s,u,w,AccountInput(id=account,nombre='Banco')),user,user)
        with migrator.begin() as c:c.execute(text('INSERT INTO public.miembros_espacio VALUES (:u,:s,:r)'),
            [{'u':reader,'s':owner,'r':'lector'},{'u':editor,'s':owner,'r':'editor'}])
        call(lambda s,u,w:create_income(s,u,w,bank,IncomeInput(id=uuid4(),fecha='2026-11-17',descripcion='Inicial',moneda='ARS',importe='1000')))
        payload=body()
        with ThreadPoolExecutor(max_workers=2) as pool:created=list(pool.map(lambda _:create(payload),range(2)))
        assert created[0]==created[1] and balance()=='1000.00'
        debt=created[0];schedule=cuotas(debt['id'])['items'];q1,q2,q3=[r['id'] for r in schedule]
        assert [r['vencimiento'] for r in schedule]==['2024-01-31','2024-02-29','2024-03-31']
        assert debt['total']=='300.00' and debt['cuotas_pagadas']==0
        denied(lambda:create(body(id=payload.id,importe='101')),409)
        denied(lambda:create(body(cuenta_id=foreign)),404)
        denied(lambda:create(body(),reader),403)
        denied(lambda:create(body(),other),403)
        outside=create(body(cuenta_id=foreign),other,other)
        foreign_quota=cuotas(outside['id'],who=other,space=other)['items'][0]['id']
        denied(lambda:cuotas(outside['id']),404)
        denied(lambda:pay(foreign_quota,payment()),404)
        denied(lambda:pay(q1,payment(),reader),403)
        denied(lambda:pay(q1,payment(cuenta_id=foreign)),404)
        original=payment()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:pay(q1,original),range(2)))
        assert results[0]==results[1] and balance()=='970.00'
        partial=cuotas(debt['id'])['items'][0]
        assert (partial['pagado'],partial['pendiente'],partial['estado'])==('30.00','70.00','parcial')
        monthly=call(lambda s,u,w:monthly_installments(s,u,w,'2024-01',day=date(2024,1,31)))
        assert monthly['totales']==[{'moneda':'ARS','cuotas':1,'cuotas_pagadas':0,'total':'100.00','pagado':'30.00','pendiente':'70.00','vencido':'0.00'}]
        assert monthly['items'][0]['id']==q1 and not monthly['items'][0]['vencida']
        overdue=call(lambda s,u,w:monthly_installments(s,u,w,'2024-01',day=date(2024,2,1)))
        assert overdue['totales'][0]['vencido']=='70.00' and overdue['items'][0]['vencida']
        assert call(lambda s,u,w:monthly_installments(s,u,w,'2024-02'))['items'][0]['vencimiento']=='2024-02-29'
        assert call(lambda s,u,w:monthly_installments(s,u,w,'2023-12'))=={'mes':'2023-12','items':[],'totales':[],'next_offset':None}
        assert call(lambda s,u,w:monthly_installments(s,u,w,'2024-01'),reader)==call(lambda s,u,w:monthly_installments(s,u,w,'2024-01'))
        denied(lambda:call(lambda s,u,w:monthly_installments(s,u,w,'2024-01'),other),403)
        denied(lambda:pay(q1,payment(id=original.id,importe='31')),409)
        denied(lambda:pay(q2,original),409)
        denied(lambda:pay(q1,payment(importe='70.01')),409)
        denied(lambda:pay(q1,original,editor),409)
        general=ExpenseInput(id=uuid4(),fecha='2026-11-17',descripcion='General',moneda='ARS',importe='1')
        call(lambda s,u,w:create_expense(s,u,w,bank,general))
        denied(lambda:pay(q1,payment(id=general.id,importe='1')),409)
        assert balance()=='969.00'
        def compete(_):
            try:return pay(q1,payment(importe='60'))
            except HTTPException as e:assert e.status_code==409;return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(compete,range(2)))
        assert sum(r is not None for r in results)==1 and balance()=='909.00'
        pay(q1,payment(importe='10'))
        assert balance()=='899.00'
        assert cuotas(debt['id'])['items'][0]['estado']=='pagada'
        remaining=next(r for r in listed() if r['id']==debt['id'])
        assert remaining['cuotas_pagadas']==1 and remaining['pendiente']=='200.00'
        # La transaccion revierte gasto y enlace aunque el fallo ocurra despues del pago.
        try:
            with runtime_transaction(runtime,usuario_id=owner,espacio_id=owner) as s:
                pay_installment(s,owner,owner,q2,payment(importe='20'))
                raise RuntimeError('rollback de prueba')
        except RuntimeError:pass
        assert balance()=='899.00' and cuotas(debt['id'])['items'][1]['pagado']=='0.00'
        pay(q2,payment(importe='100'));pay(q3,payment(importe='100'))
        finished=next(r for r in listed() if r['id']==debt['id'])
        assert finished['cuotas_pagadas']==3 and finished['pendiente']=='0.00' and finished['proximo_vencimiento'] is None
        assert balance()=='699.00'
        settled=call(lambda s,u,w:monthly_installments(s,u,w,'2024-01'))
        assert settled['totales'][0]['cuotas_pagadas']==1 and settled['totales'][0]['vencido']=='0.00'
        assert settled['totales'][0]['pendiente']=='0.00'
        # Un pago no se puede alterar desde Gastos ni por UPDATE runtime.
        source=call(lambda s,u,w:s.execute(text('SELECT * FROM public.gastos WHERE id=:id'),{'id':original.id}).mappings().one())
        edit_original=ExpenseInput(id=original.id,fecha=source['fecha'].isoformat(),descripcion=source['descripcion'],moneda='ARS',importe='30.00')
        changed=ExpenseInput(**(edit_original.model_dump(mode='json')|{'importe':'31.00'}))
        denied(lambda:call(lambda s,u,w:edit_expense(s,u,w,bank,original.id,ExpenseEdit(original=edit_original,nuevo=changed))),409)
        assert call(lambda s,u,w:s.execute(text('UPDATE public.gastos SET importe=31 WHERE id=:id'),{'id':original.id}).rowcount)==0
        assert balance()=='699.00'
        # El resumen no se limita a la primera pagina de pagos ni de cuotas.
        micro=create(body(nombre='Muchos pagos',total_cuotas=1))
        microq=cuotas(micro['id'])['items'][0]['id']
        for _ in range(101):pay(microq,payment(importe='0.10'))
        first=call(lambda s,u,w:list_payments(s,u,w,microq));following=call(lambda s,u,w:list_payments(s,u,w,microq,first['next_offset']))
        assert len(first['items'])==100 and len(following['items'])==1
        assert len({r['id'] for r in first['items']+following['items']})==101
        assert cuotas(micro['id'])['items'][0]['pagado']=='10.10' and balance()=='688.90'
        long=create(body(nombre='Calendario largo',total_cuotas=101),editor)
        first=cuotas(long['id']);following=cuotas(long['id'],first['next_offset'])
        assert len(first['items'])==100 and len(following['items'])==1 and following['items'][0]['numero']==101
        assert len(listed())==3
        assert call(lambda s,u,w:list_commitments(s,u,w),reader)==call(lambda s,u,w:list_commitments(s,u,w))
        denied(lambda:call(lambda s,u,w:list_payments(s,u,w,q1),other),403)
        with runtime.begin() as c:
            for table in ['compromisos','cuotas','pagos_cuota']:assert c.execute(text(f'SELECT count(*) FROM public.{table}')).scalar_one()==0
        sql_denied(lambda:call(lambda s,u,w:s.execute(text('DELETE FROM public.pagos_cuota'))),'42501')
        # Ambas FK del pago preservan el espacio, incluso como migrator.
        with migrator.begin() as c:
            foreign_expense=uuid4()
            c.execute(text("""INSERT INTO public.gastos(id,espacio_id,cuenta_id,usuario_id,fecha,descripcion,moneda,importe)
                VALUES (:id,:s,:a,:u,'2026-11-17','Otro','ARS',1)"""),{'id':foreign_expense,'s':other,'a':foreign,'u':other})
        for expense_id,quota_id in [(foreign_expense,q1),(general.id,foreign_quota)]:
            try:
                with migrator.begin() as c:c.execute(text('INSERT INTO public.pagos_cuota(id,espacio_id,cuota_id) VALUES (:id,:s,:q)'),{'id':expense_id,'s':owner,'q':quota_id})
            except DBAPIError as e:assert e.orig.sqlstate=='23503'
            else:raise AssertionError('Pago cruzado aceptado')
        # Totales completos por moneda aunque la pagina tenga solo 100 cuotas.
        batch=[]
        for index in range(101):
            batch.append(create(body(nombre='Mensual '+str(index),moneda='USD' if index%2 else 'ARS',
                importe='0.10',total_cuotas=1,primer_vencimiento='2040-12-31')))
        paged=call(lambda s,u,w:monthly_installments(s,u,w,'2040-12'))
        next_page=call(lambda s,u,w:monthly_installments(s,u,w,'2040-12',paged['next_offset']))
        assert len(paged['items'])==100 and len(next_page['items'])==1
        assert len({r['id'] for r in paged['items']+next_page['items']})==101
        assert paged['totales']==next_page['totales']
        assert [(t['moneda'],t['cuotas'],t['total']) for t in paged['totales']]==[('ARS',51,'5.10'),('USD',50,'5.00')]
        empty_page=call(lambda s,u,w:monthly_installments(s,u,w,'2040-12',200))
        assert not empty_page['items'] and empty_page['totales']==paged['totales']
        assert all(r['espacio_id']==str(owner) for r in paged['items'])
        assert create(payload)['cuotas_pagadas']==3
        with migrator.begin() as c:c.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u AND espacio_id=:s'),{'u':editor,'s':owner})
        denied(lambda:create(body(),editor),403)
        print('OK: planes finitos, calendario anclado, pagos parciales, reintentos y sobrepago concurrente, rollback atomico, gastos inmutables, >100 pagos/cuotas y RLS.',flush=True)
    finally:
        with migrator.begin() as c:
            for table in ['pagos_cuota','cuotas','compromisos','gastos','ingresos','cuentas']:
                for user in users:c.execute(text(f'DELETE FROM public.{table} WHERE espacio_id=:u'),{'u':user})
            for user in users:c.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u OR espacio_id=:u'),{'u':user})
            for user in users:
                c.execute(text('DELETE FROM public.espacios WHERE id=:u'),{'u':user})
                c.execute(text('DELETE FROM public.perfiles WHERE usuario_id=:u'),{'u':user})
        runtime.dispose();migrator.dispose()
