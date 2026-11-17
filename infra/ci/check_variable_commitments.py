"""Variables: borradores, confirmacion atomica y pagos sin doble contabilizacion."""
from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import UUID,uuid4
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine,text
from sqlalchemy.exc import DBAPIError
from fastapi import HTTPException
from app.accounts import AccountInput,create_account
from app.commitments import (CommitmentInput,PaymentInput,ConfirmationsInput,create_commitment,
    list_installments,list_drafts,confirm_installments,pay_installment,monthly_installments,seed_current_installment)
from app.db.connection import create_runtime_engine,create_migration_engine
from app.db.unit_of_work import runtime_transaction


def check_variable_commitments(runtime_url,migration_url,jobs_url):
    runtime,migrator=create_runtime_engine(runtime_url),create_migration_engine(migration_url)
    jobs=create_engine(jobs_url,hide_parameters=True)
    owner,other,reader=[uuid4() for _ in range(3)]
    account,foreign=uuid4(),uuid4()
    today=datetime.now(ZoneInfo('America/Argentina/Buenos_Aires')).date()
    first=today.replace(day=1);month=first.strftime('%Y-%m')
    def call(action,who=owner,space=owner):
        with runtime_transaction(runtime,usuario_id=who,espacio_id=space) as s:return action(s,who,space)
    def create(who=owner,acc=account):
        return call(lambda s,u,w:create_commitment(s,u,w,CommitmentInput(id=uuid4(),cuenta_id=acc,
            nombre='Luz',moneda='ARS',importe='100.00',primer_vencimiento=today.isoformat(),total_cuotas=None,variable=True)),who,who)
    def quotas(identifier):return call(lambda s,u,w:list_installments(s,u,w,identifier))['items']
    def batch(items):return ConfirmationsInput(items=[dict(id=i,importe=a,version=v) for i,a,v in items])
    def confirm(body,who=owner):return call(lambda s,u,w:confirm_installments(s,u,w,body),who)
    def drafts(offset=0,who=owner):return call(lambda s,u,w:list_drafts(s,u,w,offset),who)
    def expenses():return call(lambda s,u,w:s.execute(text('SELECT count(*) FROM public.gastos')).scalar_one())
    def denied(action,status):
        try:action()
        except HTTPException as e:assert e.status_code==status
        else:raise AssertionError('Operacion invalida aceptada')
    try:
        for user in [owner,other,reader]:
            with runtime_transaction(runtime,usuario_id=user) as s:s.execute(text('SELECT public.crear_espacio_personal()'))
        for user,acc in [(owner,account),(other,foreign)]:
            call(lambda s,u,w:create_account(s,u,w,AccountInput(id=acc,nombre='Banco')),user,user)
        with migrator.begin() as c:c.execute(text("INSERT INTO public.miembros_espacio VALUES (:u,:s,'lector')"),{'u':reader,'s':owner})
        plans=[create() for _ in range(101)]
        foreign_plan=create(other,foreign)
        foreign_quota=call(lambda s,u,w:list_installments(s,u,w,foreign_plan['id']),other,other)['items'][0]['id']
        first_page=drafts();next_page=drafts(first_page['next_offset'])
        assert first_page['borradores']==101 and next_page['borradores']==101
        assert len(first_page['items'])==100 and len(next_page['items'])==1
        assert all(q['estimado'] and q['estado']=='borrador' for q in first_page['items'])
        assert len({q['id'] for q in first_page['items']+next_page['items']})==101
        assert drafts(who=reader)==drafts()
        a,b,c=[quotas(p['id'])[0]['id'] for p in plans[:3]]
        pay=PaymentInput(id=uuid4(),cuenta_id=account,fecha=today.isoformat(),importe='20.00')
        denied(lambda:call(lambda s,u,w:pay_installment(s,u,w,a,pay)),409)
        assert expenses()==0
        body=batch([(a,'120.34',1),(b,'100.00',1)])
        denied(lambda:confirm(body,reader),403)
        denied(lambda:confirm(batch([(foreign_quota,'100',1)])),404)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:confirm(body),range(2)))
        assert results[0]==results[1] and expenses()==0
        confirmed=quotas(plans[0]['id'])[0]
        assert not confirmed['estimado'] and confirmed['version']==2 and confirmed['importe']=='120.34'
        assert confirmed['estado']=='pendiente' and drafts()['borradores']==99
        # El primer cambio tambien se revierte si otra cuota del lote no esta disponible.
        invalid=batch([(c,'999',1),(UUID('ffffffff-ffff-ffff-ffff-ffffffffffff'),'100',1)])
        denied(lambda:confirm(invalid),404)
        assert quotas(plans[2]['id'])[0]['estimado'] and quotas(plans[2]['id'])[0]['importe']=='100.00'
        def compete(amount):
            try:confirm(batch([(c,amount,1)]));return True
            except HTTPException as e:assert e.status_code==409;return False
        with ThreadPoolExecutor(max_workers=2) as pool:winners=list(pool.map(compete,['70.00','80.00']))
        assert sum(winners)==1 and quotas(plans[2]['id'])[0]['version']==2
        call(lambda s,u,w:pay_installment(s,u,w,a,pay))
        assert expenses()==1 and quotas(plans[0]['id'])[0]['pendiente']=='100.34'
        assert confirm(body)==results[0] and expenses()==1
        assert call(lambda s,u,w:s.execute(text('UPDATE public.cuotas SET importe=1 WHERE id=:id'),{'id':a}).rowcount)==0
        # La generacion diaria reutiliza el periodo anterior y mantiene el nuevo como estimado.
        historic=uuid4();previous=first.replace(year=first.year-1,month=12) if first.month==1 else first.replace(month=first.month-1)
        with migrator.begin() as conn:
            conn.execute(text("""INSERT INTO public.compromisos
                (id,espacio_id,cuenta_id,usuario_id,nombre,moneda,importe,primer_vencimiento,total_cuotas,variable)
                VALUES (:id,:s,:a,:s,'Agua','ARS',50,:v,NULL,true)"""),{'id':historic,'s':owner,'a':account,'v':previous})
            conn.execute(text("""INSERT INTO public.cuotas(id,espacio_id,compromiso_id,numero,vencimiento,importe)
                VALUES (:id,:s,:c,1,:v,155.55)"""),{'id':uuid4(),'s':owner,'c':historic,'v':previous})
        with jobs.begin() as conn:assert conn.execute(text('SELECT public.generar_cuotas_mes()')).scalar_one()==1
        with jobs.begin() as conn:assert conn.execute(text('SELECT public.generar_cuotas_mes()')).scalar_one()==0
        history=quotas(historic);current=history[-1]
        assert current['estimado'] and current['importe']=='155.55'
        confirm(batch([(current['id'],'160.75',1)]))
        # La misma regla se usa al reactivar/preparar una cuota desde la API.
        future=first.replace(year=first.year+1,month=1) if first.month==12 else first.replace(month=first.month+1)
        def seed(s,u,w):
            row=s.execute(text('SELECT * FROM public.compromisos WHERE id=:id'),{'id':historic}).mappings().one()
            seed_current_installment(s,w,row,future)
        call(seed)
        assert quotas(historic)[-1]['importe']=='160.75' and quotas(historic)[-1]['estimado']
        totals=call(lambda s,u,w:monthly_installments(s,u,w,month))['totales'][0]
        assert totals['borradores']==98 and totals['estimado']=='9800.00' and totals['pagado']=='20.00'
        # Las cuotas confirmadas son inmutables tambien para runtime SQL.
        assert call(lambda s,u,w:s.execute(text('UPDATE public.cuotas SET estimado=true WHERE id=:id'),{'id':current['id']}).rowcount)==0
        print('OK: variables, >100 borradores, montos previos, confirmacion atomica concurrente, rollback, lector, aislamiento, pago posterior e inmutabilidad.',flush=True)
    finally:
        with migrator.begin() as conn:
            for table in ['pagos_cuota','cuotas','compromisos','gastos','cuentas']:
                for user in [owner,other,reader]:conn.execute(text(f'DELETE FROM public.{table} WHERE espacio_id=:u'),{'u':user})
            for user in [owner,other,reader]:conn.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u OR espacio_id=:u'),{'u':user})
            for user in [owner,other,reader]:
                conn.execute(text('DELETE FROM public.espacios WHERE id=:u'),{'u':user})
                conn.execute(text('DELETE FROM public.perfiles WHERE usuario_id=:u'),{'u':user})
        runtime.dispose();migrator.dispose();jobs.dispose()
