"""Contrato real de recurrencia fija y del rol de generacion sin acceso a datos."""
from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine,text
from sqlalchemy.exc import DBAPIError
from fastapi import HTTPException
from app.accounts import AccountInput,create_account
from app.commitments import (CommitmentInput,CommitmentPause,PaymentInput,create_commitment,
    pause_commitment,list_commitments,list_installments,pay_installment,installment_detail)
from app.db.connection import create_runtime_engine,create_migration_engine
from app.db.unit_of_work import runtime_transaction


def check_recurrences(runtime_url,migration_url,jobs_url):
    runtime,migrator=create_runtime_engine(runtime_url),create_migration_engine(migration_url)
    jobs=create_engine(jobs_url,hide_parameters=True)
    owner,other,reader=[uuid4() for _ in range(3)]
    account,foreign=uuid4(),uuid4()
    today=datetime.now(ZoneInfo('America/Argentina/Buenos_Aires')).date()
    first=today.replace(day=1);last=today.replace(day=monthrange(today.year,today.month)[1])
    def call(action,who=owner,space=owner):
        with runtime_transaction(runtime,usuario_id=who,espacio_id=space) as s:return action(s,who,space)
    def plan(**changes):
        return CommitmentInput(**(dict(id=uuid4(),cuenta_id=account,nombre='Monotributo',moneda='ARS',importe='100',
            primer_vencimiento=last.isoformat(),total_cuotas=None)|changes))
    def create(body):return call(lambda s,u,w:create_commitment(s,u,w,body))
    def listed(identifier):
        return call(lambda s,u,w:list_commitments(s,u,w,identifier=identifier))['items'][0]
    def quotas(identifier):return call(lambda s,u,w:list_installments(s,u,w,identifier))['items']
    def pause(identifier,paused,version=1,who=owner):
        return call(lambda s,u,w:pause_commitment(s,u,w,identifier,CommitmentPause(pausado=paused,version=version)),who)
    def generate():
        with jobs.begin() as c:return c.execute(text('SELECT public.generar_cuotas_mes()')).scalar_one()
    def denied(action,status):
        try:action()
        except HTTPException as e:assert e.status_code==status
        else:raise AssertionError('Operacion prohibida aceptada')
    def sql_denied(engine,sql):
        try:
            with engine.begin() as c:c.execute(text(sql))
        except DBAPIError as e:assert e.orig.sqlstate=='42501'
        else:raise AssertionError('Permiso excesivo')
    try:
        for user in [owner,other,reader]:
            with runtime_transaction(runtime,usuario_id=user) as s:s.execute(text('SELECT public.crear_espacio_personal()'))
        for user,acc in [(owner,account),(other,foreign)]:
            call(lambda s,u,w:create_account(s,u,w,AccountInput(id=acc,nombre='Banco')),user,user)
        with migrator.begin() as c:c.execute(text("INSERT INTO public.miembros_espacio VALUES (:u,:s,'lector')"),{'u':reader,'s':owner})
        payload=plan();created=create(payload);identifier=created['id']
        assert created['total_cuotas'] is None and created['total']=='100.00' and len(quotas(identifier))==1
        assert create(payload)==created
        denied(lambda:call(lambda s,u,w:create_commitment(s,u,w,plan()),reader),403)
        old=first.replace(year=first.year-1)
        denied(lambda:create(plan(primer_vencimiento=old.isoformat())),422)
        future=first.replace(year=first.year+1)
        future_plan=create(plan(primer_vencimiento=future.isoformat()))
        assert future_plan['total']=='0.00' and future_plan['proximo_vencimiento'] is None and not quotas(future_plan['id'])
        finite=create(plan(total_cuotas=2))
        denied(lambda:pause(finite['id'],True),409)
        denied(lambda:pause(identifier,True,who=reader),403)
        paused=pause(identifier,True)
        assert paused['pausado'] and paused['version']==2 and len(quotas(identifier))==1
        assert pause(identifier,True)==paused
        denied(lambda:pause(identifier,False,1),409)
        # Se puede pagar una cuota anterior aunque el plan este pausado.
        quota=quotas(identifier)[0]
        call(lambda s,u,w:pay_installment(s,u,w,quota['id'],PaymentInput(id=uuid4(),cuenta_id=account,fecha=today.isoformat(),importe='30')))
        assert listed(identifier)['pendiente']=='70.00'
        # Planes historicos creados por fixture: la tarea solo genera el mes actual.
        historic=[]
        for user,acc,paused in [(owner,account,False),(other,foreign,False),(owner,account,True)]:
            ident=uuid4();historic.append(ident)
            with migrator.begin() as c:c.execute(text("""INSERT INTO public.compromisos
                (id,espacio_id,cuenta_id,usuario_id,nombre,moneda,importe,primer_vencimiento,total_cuotas,pausado)
                VALUES (:id,:s,:a,:u,'Historico','ARS',123.45,'1900-01-31',NULL,:p)"""),
                {'id':ident,'s':user,'a':acc,'u':user,'p':paused})
        with ThreadPoolExecutor(max_workers=2) as pool:counts=list(pool.map(lambda _:generate(),range(2)))
        assert sum(counts)==2 and generate()==0
        historical=quotas(historic[0])
        assert len(historical)==1 and historical[0]['vencimiento']==last.isoformat() and historical[0]['numero']>600
        assert not quotas(historic[2]) and not quotas(future_plan['id'])
        assert len(quotas(finite['id']))==2
        assert len(call(lambda s,u,w:list_installments(s,u,w,historic[1]),other,other)['items'])==1
        denied(lambda:call(lambda s,u,w:list_installments(s,u,w,historic[1])),404)
        reactivated=pause(historic[2],False)
        assert not reactivated['pausado'] and len(quotas(historic[2]))==1 and generate()==0
        assert len(quotas(identifier))==1 and len(quotas(historic[0]))==1
        # Restriccion de periodo independiente de UUID y numero de cuota.
        try:
            with migrator.begin() as c:c.execute(text("""INSERT INTO public.cuotas(id,espacio_id,compromiso_id,numero,vencimiento,importe)
                VALUES (:id,:s,:c,99999,:v,1)"""),{'id':uuid4(),'s':owner,'c':historic[0],'v':first})
        except DBAPIError as e:assert e.orig.sqlstate=='23505'
        else:raise AssertionError('Cuota duplicada en el mismo periodo')
        for table in ['compromisos','cuotas','pagos_cuota','cuentas','gastos','comprobantes']:
            sql_denied(jobs,'SELECT * FROM public.'+table)
            sql_denied(jobs,'DELETE FROM public.'+table)
        sql_denied(jobs,'CREATE TABLE public.jobs_forbidden(id integer)')
        sql_denied(runtime,'SELECT public.generar_cuotas_mes()')
        sql_denied(jobs,'SELECT public.crear_espacio_personal()')
        with migrator.begin() as c:
            assert not c.execute(text("SELECT has_column_privilege('app_runtime','public.compromisos','importe','UPDATE')")).scalar_one()
            function=c.execute(text("""SELECT proconfig,prosecdef,pg_get_userbyid(proowner) FROM pg_proc
                WHERE oid='public.generar_cuotas_mes()'::regprocedure""")).one()
            assert function==( ['search_path=pg_catalog'],True,'app_migrator')
        yesterday = today - timedelta(days=1)
        sample = {}
        for label, due in (
            ('pendiente', yesterday), ('parcial', yesterday), ('pagada', yesterday),
            ('no_aplica', yesterday), ('estimada', yesterday), ('hoy', today),
        ):
            debt = create(plan(primer_vencimiento=due.isoformat(), total_cuotas=1))
            sample[label] = quotas(debt['id'])[0]['id']
        for label, amount in [('parcial', '40'), ('pagada', '100')]:
            payment = PaymentInput(id=uuid4(), cuenta_id=account, fecha=today.isoformat(), importe=amount)
            call(lambda s,u,w: pay_installment(s,u,w,sample[label],payment))
        with migrator.begin() as c:
            for label, column in [('no_aplica', 'no_aplica'), ('estimada', 'estimado')]:
                c.execute(text(f'UPDATE public.cuotas SET {column}=true WHERE id=:id'), {'id':sample[label]})

        def mark():
            with jobs.begin() as c:
                # Un CURRENT_DATE de la sesión distinto del día argentino no adelanta ni retrasa el marcado.
                c.execute(text("SET LOCAL TIME ZONE 'Pacific/Kiritimati'"))
                if c.execute(text('SELECT CURRENT_DATE')).scalar_one() == today:
                    c.execute(text("SET LOCAL TIME ZONE 'Etc/GMT+12'"))
                assert c.execute(text('SELECT CURRENT_DATE')).scalar_one() != today
                return c.execute(text('SELECT public.marcar_cuotas_vencidas()')).scalar_one()

        sql_denied(runtime, 'SELECT public.marcar_cuotas_vencidas()')
        sql_denied(jobs, 'UPDATE public.cuotas SET marcada_vencida_el=CURRENT_DATE')
        with ThreadPoolExecutor(max_workers=2) as pool:
            marks = list(pool.map(lambda _:mark(), range(2)))
        assert max(marks) >= 2 and min(marks) == 0 and mark() == 0
        with migrator.begin() as c:
            for label, identifier in sample.items():
                stored = c.execute(text('SELECT marcada_vencida_el FROM public.cuotas WHERE id=:id'),
                                   {'id': identifier}).scalar_one()
                assert stored == (today if label in ('pendiente', 'parcial') else None)
        payment = PaymentInput(id=uuid4(), cuenta_id=account, fecha=today.isoformat(), importe='60')
        call(lambda s,u,w: pay_installment(s,u,w,sample['parcial'],payment))
        detail = call(lambda s,u,w: installment_detail(s,u,w,sample['parcial']))
        assert detail['estado'] == 'pagada' and not detail['vencida']
        print('OK: marcado diario de cuotas vencidas por fecha argentina y saldo pendiente.', flush=True)
        print('OK: gastos indefinidos, pausa versionada, reactivacion, pagos conservados, periodo unico, generacion concurrente independiente y rol jobs restringido.',flush=True)
    finally:
        with migrator.begin() as c:
            for table in ['pagos_cuota','cuotas','compromisos','gastos','cuentas']:
                for user in [owner,other,reader]:c.execute(text(f'DELETE FROM public.{table} WHERE espacio_id=:u'),{'u':user})
            for user in [owner,other,reader]:c.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u OR espacio_id=:u'),{'u':user})
            for user in [owner,other,reader]:
                c.execute(text('DELETE FROM public.espacios WHERE id=:u'),{'u':user})
                c.execute(text('DELETE FROM public.perfiles WHERE usuario_id=:u'),{'u':user})
        runtime.dispose();migrator.dispose();jobs.dispose()
