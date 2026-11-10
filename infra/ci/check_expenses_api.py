"""Gastos: dinero exacto, aislamiento y reintento contra la base desechable."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from app.accounts import AccountInput, create_account
from app.expenses import list_similar_expenses, category_suggestion, ExpenseFilters, ExpenseInput, ExpenseEdit, edit_expense, create_expense, list_expenses
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
        insert="INSERT INTO public.gastos(id,espacio_id,cuenta_id,usuario_id,fecha,descripcion,moneda,importe) VALUES (:id,:s,:a,:u,'2026-11-06','SQL','ARS',1)"
        params={'id':uuid4(),'s':owner,'a':account,'u':other}
        sql_denied(owner,insert,params,'42501')
        sql_denied(reader,insert,params|{'u':reader},'42501')
        sql_denied(owner,'DELETE FROM public.gastos',{},'42501')
        def edit(who,space,acct,original,nuevo):
            with runtime_transaction(runtime,usuario_id=who,espacio_id=space) as s:
                return edit_expense(s,who,space,acct,payload.id,ExpenseEdit(original=original,nuevo=nuevo))
        changed=body(id=payload.id,fecha='2026-11-01',importe='0.25')
        saved=edit(editor,owner,account,payload,changed)
        assert saved['fecha']=='2026-11-01' and saved['importe']=='0.25' and saved['id']==str(payload.id)
        assert edit(editor,owner,account,payload,changed)==saved
        denied(lambda:edit(owner,owner,account,payload,body(id=payload.id,importe='2')),409)
        denied(lambda:edit(reader,owner,account,changed,payload),403)
        denied(lambda:edit(other,owner,account,changed,payload),403)
        denied(lambda:edit(owner,owner,foreign,changed,payload),404)
        sql_denied(owner,'UPDATE public.gastos SET cuenta_id=:a',{'a':foreign},'42501')
        with runtime_transaction(runtime,usuario_id=reader,espacio_id=owner) as s:
            assert s.execute(text('UPDATE public.gastos SET importe=2')).rowcount==0
        with runtime_transaction(runtime,usuario_id=other,espacio_id=other) as s:
            assert s.execute(text('UPDATE public.gastos SET importe=2 WHERE id=:id'),{'id':payload.id}).rowcount==0
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
        # Clasificar existentes no cambia sus IDs; un cliente anterior conserva la categoria.
        categorized=body(id=payload.id,fecha=changed.fecha.isoformat(),importe='0.25',categoria='alimentos')
        assert edit(editor,owner,account,changed,categorized)['categoria']=='alimentos'
        legacy=body(id=payload.id,fecha='2026-11-02',importe='0.25')
        assert edit(editor,owner,account,changed,legacy)['categoria']=='alimentos'
        denied(lambda:edit(editor,owner,account,categorized,body(id=payload.id,categoria='ocio')),409)
        # Una categoria no valida tampoco puede escribirse por SQL directo.
        sql_denied(owner,"UPDATE public.gastos SET categoria='inventada' WHERE id=:id",{'id':payload.id},'23514')
        with runtime_transaction(runtime,usuario_id=reader,espacio_id=owner) as s:
            assert s.execute(text("UPDATE public.gastos SET categoria='ocio'")).rowcount==0
        def filtered(who=owner,space=owner,acct=account,offset=0,**kw):
            with runtime_transaction(runtime,usuario_id=who,espacio_id=space) as s:
                return list_expenses(s,who,space,acct,offset,ExpenseFilters(**kw))
        result=filtered(desde='2026-11-02',hasta='2026-11-02',categoria='alimentos',moneda='ARS',texto='COMI')
        assert [r['id'] for r in result['items']]==[str(payload.id)]
        assert not filtered(hasta='2026-11-01',categoria='alimentos')['items']
        assert len(filtered(categoria='sin_categoria')['items'])==100
        assert not filtered(texto="%' OR true --")['items']
        denied(lambda:filtered(desde='2026-12-01',hasta='2026-11-01'),422)
        denied(lambda:filtered(who=other),403)
        denied(lambda:filtered(acct=foreign),404)
        # Mas de una pagina de coincidencias: filtros antes de LIMIT/OFFSET.
        with migrator.begin() as c:
            c.execute(text("INSERT INTO public.gastos(id,espacio_id,cuenta_id,usuario_id,fecha,descripcion,moneda,importe,categoria) VALUES (:id,:s,:a,:u,'2026-10-01','Cerveza 10%_oferta','ARS',1,'ocio')"),[params|{'id':uuid4(),'u':owner} for _ in range(102)])
        page=filtered(texto='cerveza',categoria='ocio'); following=filtered(offset=page['next_offset'],texto='cerveza',categoria='ocio')
        assert len(page['items'])==100 and len(following['items'])==2 and following['next_offset'] is None
        assert len({r['id'] for r in page['items']+following['items']})==102
        assert filtered(texto='10%_oferta')['next_offset']==100
        assert not filtered(texto='10X_oferta')['items']
        for typo in ['cervesa','cerbeza','serbesa']:
            page=filtered(texto=typo,categoria='ocio',moneda='ARS',desde='2026-10-01',hasta='2026-10-01')
            following=filtered(offset=page['next_offset'],texto=typo,categoria='ocio',moneda='ARS',desde='2026-10-01',hasta='2026-10-01')
            assert len(page['items'])==100 and len(following['items'])==2
            assert all(r['coincidencia_aproximada'] for r in page['items']+following['items'])
            assert len({r['id'] for r in page['items']+following['items']})==102
            assert not filtered(texto=typo,aproximada=False)['items']
            assert not filtered(texto=typo,categoria='alimentos')['items']
            assert not filtered(texto=typo,moneda='USD')['items']
            assert not filtered(texto=typo,desde='2026-10-02')['items']
        assert not any(r['coincidencia_aproximada'] for r in filtered(texto='CERVEZA')['items'])
        assert filtered(texto='serbesa',who=reader)['next_offset']==100
        denied(lambda:filtered(texto='serbesa',who=other),403)
        denied(lambda:filtered(texto='serbesa',acct=foreign),404)
        accented=body(descripcion='Café con leche',categoria='alimentos')
        create(owner,owner,account,accented)
        assert [r['id'] for r in filtered(texto='CAFE',aproximada=False)['items']]==[str(accented.id)]
        print('OK: busqueda aproximada, tildes, opcion literal, permisos, filtros combinados y dos paginas completas.',flush=True)
        print('OK: categorias, clientes anteriores, filtros combinados, texto literal, aislamiento y paginacion filtrada.',flush=True)
        def suggest(who=owner,space=owner,acct=account,description='Yerba mate'):
            with runtime_transaction(runtime,usuario_id=who,espacio_id=space) as session:
                return category_suggestion(session,who,space,acct,description)
        assert suggest()['categoria'] is None
        create(owner,owner,account,body(descripcion='Yerba mate',categoria='alimentos'))
        assert suggest()['categoria'] is None
        create(editor,owner,account,body(descripcion='Yerba mate',categoria='alimentos'))
        create(owner,owner,account,body(descripcion='Yerba mate'))
        for _ in range(3):create(other,other,foreign,body(descripcion='Yerba mate',categoria='salud'))
        assert suggest()=={'categoria':'alimentos','coincidencias':2,'total':2}
        assert suggest(who=reader)==suggest()
        denied(lambda:suggest(who=other),403)
        denied(lambda:suggest(acct=foreign),404)
        assert suggest(who=other,space=other,acct=foreign)['categoria']=='salud'
        # No hay aprendizaje global: las cuentas del mismo espacio tambien se separan.
        second=uuid4()
        with runtime_transaction(runtime,usuario_id=owner,espacio_id=owner) as session:
            create_account(session,owner,owner,AccountInput(id=second,nombre='Segunda'))
        assert suggest(acct=second)['categoria'] is None
        create(owner,owner,account,body(descripcion='Yerba mate',categoria='ocio'))
        create(owner,owner,account,body(descripcion='Yerba mate',categoria='ocio'))
        assert suggest()['categoria'] is None
        print('OK: sugerencias por historial, abstencion, lector, aislamiento entre espacios y cuentas.',flush=True)
        reference=body(descripcion='Farmacia barrio',fecha='2025-02-09')
        create(owner,owner,account,reference)
        comparable=[]
        for day in range(1,9):
            candidate=body(descripcion='Farmacia del barrio',fecha=f'2025-02-{day:02}',moneda='USD' if day%2 else 'ARS')
            create(owner,owner,account,candidate);comparable.append(str(candidate.id))
        outside=body(descripcion='Farmacia barrio',fecha='2031-01-01')
        create(other,other,foreign,outside)
        create(owner,owner,second,body(descripcion='Farmacia barrio',fecha='2031-01-01'))
        # Los similares pueden estar detras de mas de un lote de no coincidencias.
        with migrator.begin() as c:
            c.execute(text("INSERT INTO public.gastos(id,espacio_id,cuenta_id,usuario_id,fecha,descripcion,moneda,importe) VALUES (:id,:s,:a,:u,'2030-01-01','Seguro del auto','ARS',1)"),[params|{'id':uuid4(),'u':owner} for _ in range(210)])
        def similar(who=owner,space=owner,acct=account,expense=reference.id):
            with runtime_transaction(runtime,usuario_id=who,espacio_id=space) as session:
                return list_similar_expenses(session,who,space,acct,expense)
        result=similar()
        assert result['referencia_id']==str(reference.id)
        assert [r['id'] for r in result['items']]==list(reversed(comparable))[:5]
        assert {r['moneda'] for r in result['items']}=={'ARS','USD'}
        assert all(r['coincidencia_aproximada'] and r['importe']=='0.10' for r in result['items'])
        assert similar(who=reader)==result
        denied(lambda:similar(who=other),403)
        denied(lambda:similar(acct=foreign),404)
        denied(lambda:similar(expense=outside.id),404)
        denied(lambda:similar(expense=uuid4()),404)
        print('OK: cinco similares recientes, exclusion del original, monedas exactas, lectura y aislamiento.',flush=True)
        with migrator.begin() as c: c.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u AND espacio_id=:s'),{'u':editor,'s':owner})
        denied(lambda:create(editor,owner,account,body()),403)
        denied(lambda:similar(who=editor),403)
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
