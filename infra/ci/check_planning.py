"""Pruebas del plan compartido en la base desechable de CI."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from app.planning import PlanUpdate,get_category_limit_history,get_plan,save_plan,EMPTY
from app.db.connection import create_runtime_engine,create_migration_engine
from app.db.unit_of_work import runtime_transaction

def check_planning(runtime_url,migration_url):
    runtime,migrator=create_runtime_engine(runtime_url),create_migration_engine(migration_url)
    owner,other,reader,editor=[uuid4() for _ in range(4)];users=[owner,other,reader,editor]
    def read(who=owner,space=owner):
        with runtime_transaction(runtime,usuario_id=who,espacio_id=space) as s:return get_plan(s,who,space)
    def save(value,who=owner,space=owner):
        with runtime_transaction(runtime,usuario_id=who,espacio_id=space) as s:return save_plan(s,who,space,PlanUpdate(**value))
    def history(month, who=owner):
        with runtime_transaction(runtime, usuario_id=who, espacio_id=owner) as s:
            return get_category_limit_history(s, who, owner, month)
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
        current = read()
        category_limits = [{'categoria': 'alimentos', 'moneda': 'ARS', 'importe': '30000.00'}]
        with_limit = save({'version': 2, 'datos': current['datos'] | {'limites_categoria': category_limits}}, editor)
        assert with_limit['version'] == 3 and read(reader)['datos']['limites_categoria'] == category_limits
        denied(lambda: save({'version': 3, 'datos': current['datos']}, reader), 403)
        with migrator.begin() as c:
            month = c.execute(text("""
                SELECT to_char(statement_timestamp() AT TIME ZONE 'America/Argentina/Buenos_Aires', 'YYYY-MM')
            """)).scalar_one()
            c.execute(text("""
                UPDATE public.planes_gasto
                SET historial_categoria = historial_categoria || jsonb_build_object('2000-01', datos->'limites_categoria')
                WHERE espacio_id=:s
            """), {'s': owner})
        assert history('1999-12', reader) is None
        assert history('2000-02', reader) == category_limits
        assert history(month, reader) == category_limits
        denied(lambda: history(month, other), 403)
        try:
            with runtime_transaction(runtime, usuario_id=owner, espacio_id=owner) as s:
                s.execute(text("UPDATE public.planes_gasto SET historial_categoria='{}'"))
        except DBAPIError as error:
            assert error.orig.sqlstate == '42501'
        else:
            raise AssertionError('Runtime pudo editar directamente el historial de límites')

        legacy_data = current['datos'] | {'limites': {'diario': None, 'semanal': None}}
        legacy_write = save({'version': 3, 'datos': legacy_data})
        assert legacy_write == {'version': 4, 'datos': legacy_data | {'limites_categoria': category_limits}}
        assert save({'version': 3, 'datos': legacy_data}) == legacy_write
        cleared = save({'version': 4, 'datos': legacy_data | {'limites_categoria': []}})
        assert cleared == {'version': 5, 'datos': legacy_data}
        assert history(month, reader) == []
        assert history('2000-02', reader) == category_limits
        monthly_limit = {'moneda': 'ARS', 'importe': '12345.00'}
        monthly_data = legacy_data | {'limites': legacy_data['limites'] | {'mensual': monthly_limit}}
        assert save({'version': 5, 'datos': monthly_data}) == {'version': 6, 'datos': monthly_data}

        legacy_limits = legacy_data['limites'] | {'diario': {'moneda': 'ARS', 'importe': '500.00'}}
        legacy_edit = legacy_data | {'limites': legacy_limits}
        preserved = legacy_data | {'limites': legacy_limits | {'mensual': monthly_limit}}
        assert save({'version': 6, 'datos': legacy_edit}) == {'version': 7, 'datos': preserved}

        clear_monthly = legacy_data | {'limites': legacy_limits | {'mensual': None}}
        assert save({'version': 7, 'datos': clear_monthly}) == {'version': 8, 'datos': legacy_edit}

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
