"""Gastos: dinero exacto, aislamiento y reintento contra la base desechable."""
import csv
import io
from datetime import date
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from zipfile import ZipFile
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from app.accounts import AccountInput, create_account
from app.expenses import expense_category_summary, expense_summary, expense_trend, list_similar_expenses, category_suggestion, ExpenseFilters, ExpenseInput, ExpenseEdit, edit_expense, create_expense, list_expenses
from app.expenses import void_expense
from app.expense_import import ImportRequest, cancel_batch, import_rows, recent_batches
from app.incomes import account_balance
from app.movements import list_movements
from app.movement_categories import CategoryCreate, CategoryUpdate, list_categories, save_category
from app.space_export import build_export
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
        # Global sums must include >100 rows, another account, and respect RLS.
        for day,amount in [('2024-02-01','2.00'),('2024-02-29','3.00'),('2024-03-01','9.00')]:
            create(owner,owner,second,body(fecha=day,importe=amount))
        for _ in range(101): create(owner,owner,account,body(fecha='2024-02-29',importe='0.10'))
        create(other,other,foreign,body(fecha='2024-02-29',importe='999.00'))
        def summary(who=owner,space=owner,acct=None):
            with runtime_transaction(runtime,usuario_id=who,espacio_id=space) as session:
                return expense_summary(session,who,space,acct,date(2024,2,29))
        assert summary()['totales']==[{'moneda':'ARS','dia':'13.10','mes':'15.10','semana':'22.10'}]
        assert summary(acct=account)['totales']==[{'moneda':'ARS','dia':'10.10','mes':'10.10','semana':'10.10'}]
        assert summary(who=reader)==summary()
        denied(lambda:summary(who=other),403)
        denied(lambda:summary(acct=foreign),404)
        with runtime_transaction(runtime,usuario_id=owner,espacio_id=owner) as session:
            all_page=list_expenses(session,owner,owner,None,filters=ExpenseFilters(desde='2024-02-01',hasta='2024-02-29'))
            more=list_expenses(session,owner,owner,None,all_page['next_offset'],ExpenseFilters(desde='2024-02-01',hasta='2024-02-29'))
            combined=all_page['items']+more['items']
            assert len(combined)==103 and {r['cuenta_id'] for r in combined}=={str(account),str(second)}
        print('OK: todas las cuentas, sumas completas, mes bisiesto, lector y aislamiento del resumen.',flush=True)

        create(owner, owner, second, body(fecha='2024-02-28', categoria='alimentos', importe='8.50'))
        create(owner, owner, account, body(fecha='2024-02-28', categoria='alimentos', moneda='USD', importe='2.00'))
        def category_summary(who=owner, acct=None):
            with runtime_transaction(runtime, usuario_id=who, espacio_id=owner) as session:
                return expense_category_summary(session, who, owner, acct, date(2024, 2, 29))
        with runtime_transaction(runtime, usuario_id=reader, espacio_id=owner) as session:
            series = expense_trend(session, reader, owner, day=date(2024, 2, 29))
        assert len(series['meses']) == 12 and series['meses'][0] == '2023-03' and series['meses'][-1] == '2024-02'
        report = category_summary()
        assert [{key: value for key, value in row.items() if key != 'mes'}
                for row in series['items'] if row['mes'] == '2024-02'] == sorted(
                    report['items'], key=lambda row: (row['moneda'], row['categoria'] is None, row['categoria'] or ''))
        assert report == {
            'desde': '2024-02-01', 'hasta': '2024-02-29',
            'items': [
                {'moneda': 'ARS', 'categoria': None, 'total': '15.10'},
                {'moneda': 'ARS', 'categoria': 'alimentos', 'total': '8.50'},
                {'moneda': 'USD', 'categoria': 'alimentos', 'total': '2.00'},
            ],
        }
        assert category_summary(who=reader) == report
        assert category_summary(acct=account)['items'] == [
            {'moneda': 'ARS', 'categoria': None, 'total': '10.10'},
            {'moneda': 'USD', 'categoria': 'alimentos', 'total': '2.00'},
        ]
        denied(lambda: category_summary(who=other), 403)
        denied(lambda: category_summary(acct=foreign), 404)

        summary_before_cancel_test = {row['moneda']: row for row in summary()['totales']}
        canceled = body(fecha='2024-02-29', importe='9.85', categoria='alimentos', nota='Café de prueba',
                        fecha_devengamiento='2024-01-28', fecha_vencimiento='2024-02-20')
        detailed = create(owner, owner, account, canceled)
        assert detailed['nota'] == canceled.nota
        assert (detailed['fecha'], detailed['fecha_devengamiento'], detailed['fecha_vencimiento']) == (
            '2024-02-29', '2024-01-28', '2024-02-20',
        )
        assert create(owner, owner, account, canceled) == detailed
        denied(lambda: create(owner, owner, account, canceled.model_copy(
            update={'fecha_vencimiento': date(2024, 2, 21)},
        )), 409)

        def cancel(who=owner, expense=canceled.id):
            with runtime_transaction(runtime, usuario_id=who, espacio_id=owner) as session:
                return void_expense(session, who, owner, account, expense)

        def history(anulados=False):
            filters = dict(desde=None, hasta=None, tipo=None, moneda=None, cuenta=account,
                           texto='CAFE de prueba', anulados=anulados)
            with runtime_transaction(runtime, usuario_id=owner, espacio_id=owner) as session:
                return list_movements(session, owner, owner, filters, None)

        def balance():
            with runtime_transaction(runtime, usuario_id=owner, espacio_id=owner) as session:
                rows = account_balance(session, owner, owner, account)['totales']
                return next(row['saldo'] for row in rows if row['moneda'] == 'ARS')

        before = balance()
        assert [row['id'] for row in history()['items']] == [str(canceled.id)]
        denied(lambda: cancel(who=reader), 403)
        denied(lambda: cancel(expense=outside.id), 404)
        assert cancel() == cancel() == {'id': str(canceled.id), 'anulado': True}
        assert Decimal(balance()) - Decimal(before) == Decimal('9.85')
        assert {row['moneda']: row for row in summary()['totales']} == summary_before_cancel_test
        assert category_summary() == report
        assert history()['items'] == []
        audited = history(anulados=True)
        assert [(row['id'], row['anulado']) for row in audited['items']] == [(str(canceled.id), True)]
        assert audited['totales'] == []

        custom = CategoryCreate(id=str(uuid4()), tipo='gasto', nombre='Comida Casa', color='#64748b')

        def category_write(who, space, category, changes, create=False):
            with runtime_transaction(runtime, usuario_id=who, espacio_id=space) as session:
                return save_category(session, who, space, 'gasto', category, changes, create=create)

        def categories(who, space):
            with runtime_transaction(runtime, usuario_id=who, espacio_id=space) as session:
                return list_categories(session, who, space)['items']

        assert any(row['id'] == 'sueldo' and row['tipo'] == 'ingreso' for row in categories(reader, owner))
        denied(lambda: category_write(reader, owner, custom.id, custom, create=True), 403)
        assert category_write(editor, owner, custom.id, custom, create=True)['nombre'] == 'Comida Casa'
        duplicate = CategoryCreate(id=str(uuid4()), tipo='gasto', nombre='comidaCASA')
        denied(lambda: category_write(owner, owner, duplicate.id, duplicate, create=True), 409)
        assert all(row['id'] != custom.id for row in categories(other, other))
        recorded = body(categoria=custom.id)
        assert create(owner, owner, account, recorded)['categoria'] == custom.id
        category_write(owner, owner, custom.id, CategoryUpdate(nombre='Comida hogar', activa=False))
        assert create(owner, owner, account, recorded)['categoria'] == custom.id
        denied(lambda: create(owner, owner, account, body(categoria=custom.id)), 422)
        assert any(row['id'] == custom.id and row['nombre'] == 'Comida hogar' and not row['activa']
                   for row in categories(reader, owner))

        formula = body(descripcion='=1+1', nota='Café, casa', importe='0.10')
        create(owner, owner, account, formula)

        def export_as(user):
            with runtime_transaction(runtime, usuario_id=user, espacio_id=owner, repeatable_read=True) as session:
                assert session.execute(text('SHOW transaction_isolation')).scalar_one() == 'repeatable read'
                return build_export(session, user, owner)

        denied(lambda: export_as(reader), 403)
        denied(lambda: export_as(editor), 403)
        denied(lambda: export_as(other), 403)
        with ZipFile(io.BytesIO(export_as(owner))) as archive:
            assert archive.testzip() is None
            assert {'LEEME.txt', 'cuentas.csv', 'gastos.csv', 'compromisos.csv', 'preferencias_avisos.csv'} <= set(archive.namelist())
            rows = list(csv.DictReader(io.StringIO(archive.read('gastos.csv').decode('utf-8-sig'))))
            assert len(rows) > 100 and all(row['cuenta_id'] != str(foreign) for row in rows)
            assert 'usuario_id' not in rows[0]
            exported = next(row for row in rows if row['id'] == str(formula.id))
            assert (exported['descripcion'], exported['nota'], exported['importe']) == ("'=1+1", 'Café, casa', '0.10')
            canceled_row = next(row for row in rows if row['id'] == str(canceled.id))
            assert canceled_row['anulado_en']
            assert (canceled_row['fecha_devengamiento'], canceled_row['fecha_vencimiento']) == ('2024-01-28', '2024-02-20')
            catalog = list(csv.DictReader(io.StringIO(archive.read('categorias.csv').decode('utf-8-sig'))))
            assert any(row['id'] == custom.id and row['nombre'] == 'Comida hogar' and row['activa'] == 'False' for row in catalog)
            assert 'ruta' not in archive.read('comprobantes.csv').decode('utf-8-sig')

        def expense_details(due):
            return body(id=payload.id, fecha=legacy.fecha.isoformat(), importe='0.25', fecha_vencimiento=due)

        absent = expense_details(None)
        due = expense_details('2026-10-25')
        saved = edit(editor, owner, account, absent, due)
        assert saved['fecha_vencimiento'] == '2026-10-25'
        assert edit(editor, owner, account, absent, due) == saved
        denied(lambda: edit(editor, owner, account, absent, expense_details('2026-10-20')), 409)
        assert 'fecha_vencimiento' not in edit(editor, owner, account, due, absent)

        import_data = dict(fecha='2024-02-20', descripcion='Importación de prueba', moneda='ARS', importe='0.10')
        preview_body = ImportRequest(filas=[import_data, import_data])

        def import_as(request, write=False, who=owner):
            with runtime_transaction(runtime, usuario_id=who, espacio_id=owner) as session:
                return import_rows(session, who, owner, account, request, commit=write)

        before_import = balance()
        denied(lambda: import_as(preview_body, who=reader), 403)
        invalid = ImportRequest(filas=[import_data | {'fecha': '2024-02-30'}])
        denied(lambda: import_as(invalid), 422)
        preview = import_as(preview_body)
        assert preview['nuevas'] == 2 and preview['duplicadas'] == []
        assert balance() == before_import
        batch = uuid4()
        confirm = ImportRequest(filas=[import_data, import_data], lote=batch, revision=preview['revision'])
        assert import_as(confirm, write=True) == import_as(confirm, write=True) == {'lote': batch, 'importadas': 2}
        assert Decimal(before_import) - Decimal(balance()) == Decimal('0.20')
        assert import_as(preview_body)['duplicadas'] == [0, 1]
        denied(lambda: import_as(confirm.model_copy(update={'lote': uuid4()}), write=True), 409)
        with runtime_transaction(runtime, usuario_id=owner, espacio_id=owner) as session:
            assert recent_batches(session, owner, owner, account)['items'][0]['lote'] == batch
            assert cancel_batch(session, owner, owner, second, batch) == {'anuladas': 0}
            assert cancel_batch(session, owner, owner, account, batch) == {'anuladas': 2}
            assert cancel_batch(session, owner, owner, account, batch) == {'anuladas': 0}
        assert balance() == before_import
        assert import_as(preview_body)['nuevas'] == 2

        manual = body(**import_data)
        create(owner, owner, account, manual)
        create(owner, owner, second, body(**import_data))
        with_manual = import_as(preview_body)
        assert with_manual['nuevas'] == 1 and with_manual['duplicadas'] == []
        assert with_manual['coincidencias_manuales'] == [0]
        include = preview_body.model_copy(update={'incluir_coincidencias_manuales': True})
        assert import_as(include)['nuevas'] == 2
        denied(lambda: import_as(confirm.model_copy(update={'lote': uuid4()}), write=True), 409)
        extra_batch = uuid4()
        extra = confirm.model_copy(update={'lote': extra_batch, 'revision': with_manual['revision']})
        assert import_as(extra, write=True)['importadas'] == 1
        both = import_as(preview_body)
        assert both['nuevas'] == 0 and both['duplicadas'] == [1] and both['coincidencias_manuales'] == [0]
        with runtime_transaction(runtime, usuario_id=owner, espacio_id=owner) as session:
            assert cancel_batch(session, owner, owner, account, extra_batch) == {'anuladas': 1}
            assert session.execute(text('SELECT anulado_en FROM public.gastos WHERE id=:id'),
                                   {'id': manual.id}).scalar_one() is None

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
