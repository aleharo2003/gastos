"""Pruebas del plan compartido en la base desechable de CI."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from app.planning import PlanUpdate,get_plan,save_plan,EMPTY
from app.db.connection import create_runtime_engine,create_migration_engine
from app.db.unit_of_work import runtime_transaction

def check_planning(runtime_url,migration_url):
    runtime,migrator=create_runtime_engine(runtime_url),create_migration_engine(migration_url)
    owner,other,reader,editor=[uuid4() for _ in range(4)];users=[owner,other,reader,editor]
    def read(who=owner,space=owner):
        with runtime_transaction(runtime,usuario_id=who,espacio_id=space) as s:return get_plan(s,who,space)
    def save(value,who=owner,space=owner):
        with runtime_transaction(runtime,usuario_id=who,espacio_id=space) as s:return save_plan(s,who,space,PlanUpdate(**value))
    def denied(action,code):
        try:action()
        except HTTPException as e:assert e.status_code==code
        else:raise AssertionError('Acceso inesperado')
    data={'limites':{'diario':None,'semanal':{'moneda':'USD','importe':'200.00'}},'conceptos':[{'id':str(uuid4()),'concepto':'Verduras','frecuencia':'semana','moneda':'ARS','importe':'30000.00'}]}
    try:
        for user in users:
            with runtime_transaction(runtime,usuario_id=user) as s:s.execute(text('SELECT public.crear_espacio_personal()'))
        with migrator.begin() as c:c.execute(text('INSERT INTO public.miembros_espacio VALUES (:u,:s,:r)'),[{'u':reader,'s':owner,'r':'lector'},{'u':editor,'s':owner,'r':'editor'}])
        assert read()=={'version':0,'datos':EMPTY}
        first=save({'version':0,'datos':data});assert first=={'version':1,'datos':data}
        assert save({'version':0,'datos':data})==first # lost response retry
        assert read(reader)==first and read(other,other)=={'version':0,'datos':EMPTY}
        denied(lambda:read(other),403);denied(lambda:save({'version':1,'datos':EMPTY},reader),403)
        denied(lambda:save({'version':0,'datos':EMPTY}),409)
        def concurrent(amount):
            proposal={'limites':{'diario':None,'semanal':{'moneda':'USD','importe':amount}},'conceptos':[]}
            try:return save({'version':1,'datos':proposal},editor)['version']
            except HTTPException as e:return e.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(concurrent,['210.00','220.00']))
        assert sorted(outcomes)==[2,409]
        with runtime_transaction(runtime,usuario_id=other,espacio_id=other) as s:
            assert s.execute(text('SELECT count(*) FROM public.planes_gasto')).scalar_one()==0
            assert s.execute(text('UPDATE public.planes_gasto SET version=99 WHERE espacio_id=:s'),{'s':owner}).rowcount==0
        try:
            with runtime_transaction(runtime,usuario_id=owner,espacio_id=owner) as s:s.execute(text('DELETE FROM public.planes_gasto'))
        except DBAPIError as e:assert e.orig.sqlstate=='42501'
        else:raise AssertionError('Runtime pudo borrar el plan')
        with migrator.begin() as c:
            assert c.execute(text('SELECT count(*) FROM public.gastos WHERE espacio_id=:s'),{'s':owner}).scalar_one()==0
            assert c.execute(text('UPDATE public.planes_gasto SET version=version+1 WHERE espacio_id=:s'),{'s':owner}).rowcount==1
            c.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u AND espacio_id=:s'),{'u':editor,'s':owner})
        denied(lambda:read(editor),403)
        print('OK: planes compartidos, lector, aislamiento, conflictos concurrentes, reintento, revocacion y sin gastos creados.',flush=True)
    finally:
        with migrator.begin() as c:
            for user in users:c.execute(text('DELETE FROM public.planes_gasto WHERE espacio_id=:u'),{'u':user})
            for user in users:c.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u OR espacio_id=:u'),{'u':user})
            for user in users:
                c.execute(text('DELETE FROM public.espacios WHERE id=:u'),{'u':user});c.execute(text('DELETE FROM public.perfiles WHERE usuario_id=:u'),{'u':user})
        runtime.dispose();migrator.dispose()
