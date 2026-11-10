"""Base temporal real y Storage doble en memoria; no usa archivos del usuario."""
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import text
from app.accounts import AccountInput, create_account
from app.expenses import ExpenseInput, create_expense
from app.receipts import save_receipt, download_receipt, list_receipts
from app.db.connection import create_runtime_engine, create_migration_engine
from app.db.unit_of_work import runtime_transaction


def check_receipts(runtime_url,migration_url):
    runtime,migrator=create_runtime_engine(runtime_url),create_migration_engine(migration_url)
    owner,other,reader,editor=[uuid4() for _ in range(4)];users=[owner,other,reader,editor]
    account,expense,receipt=uuid4(),uuid4(),uuid4()
    class Storage:
        def __init__(self):self.files={};self.fail=False
        def put(self,path,data,mime):
            if self.fail:raise HTTPException(503,'simulado')
            self.files[path]=data
        def get(self,path):return self.files[path]
    storage=Storage();data=b'%PDF-1.7\n%%EOF'
    def upload(who=owner,rid=receipt,body=data,space=owner):
        with runtime_transaction(runtime,usuario_id=who,espacio_id=space) as s:
            return save_receipt(s,who,space,account,expense,rid,'ticket.pdf',body,storage)
    def denied(action,code):
        try:action()
        except HTTPException as e:assert e.status_code==code,(e.status_code,code)
        else:raise AssertionError('Se acepto operacion no permitida')
    try:
        for user in users:
            with runtime_transaction(runtime,usuario_id=user) as s:s.execute(text('SELECT public.crear_espacio_personal()'))
        with runtime_transaction(runtime,usuario_id=owner,espacio_id=owner) as s:
            create_account(s,owner,owner,AccountInput(id=account,nombre='Cuenta de prueba'))
            create_expense(s,owner,owner,account,ExpenseInput(id=expense,fecha='2026-11-06',descripcion='Prueba',moneda='ARS',importe='1'))
        with migrator.begin() as c:c.execute(text('INSERT INTO public.miembros_espacio VALUES (:u,:s,:r)'),[{'u':reader,'s':owner,'r':'lector'},{'u':editor,'s':owner,'r':'editor'}])
        first=upload();assert upload()==first;assert len(storage.files)==1
        denied(lambda:upload(body=b'%PDF-otro\n%%EOF'),409)
        denied(lambda:upload(reader,uuid4()),403);denied(lambda:upload(other,uuid4()),403)
        with runtime_transaction(runtime,usuario_id=reader,espacio_id=owner) as s:
            assert len(list_receipts(s,reader,owner,account,expense)['items'])==1
            assert download_receipt(s,reader,owner,account,expense,receipt,storage).body==data
        with runtime_transaction(runtime,usuario_id=other,espacio_id=other) as s:
            assert s.execute(text('SELECT id FROM public.comprobantes')).all()==[]
        storage.fail=True;denied(lambda:upload(rid=uuid4()),503);storage.fail=False
        with runtime_transaction(runtime,usuario_id=owner,espacio_id=owner) as s:assert len(list_receipts(s,owner,owner,account,expense)['items'])==1
        for _ in range(4):upload(editor,uuid4())
        denied(lambda:upload(rid=uuid4()),409)
        with migrator.begin() as c:c.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u AND espacio_id=:s'),{'u':reader,'s':owner})
        def revoked():
            with runtime_transaction(runtime,usuario_id=reader,espacio_id=owner) as s:download_receipt(s,reader,owner,account,expense,receipt,storage)
        denied(revoked,403)
        print('OK: comprobantes privados, reintento, limites, rollback, lector y revocacion.',flush=True)
    finally:
        with migrator.begin() as c:
            for table in ['comprobantes','gastos','cuentas']:
                for user in users:c.execute(text(f'DELETE FROM public.{table} WHERE espacio_id=:u'),{'u':user})
            for user in users:c.execute(text('DELETE FROM public.miembros_espacio WHERE usuario_id=:u OR espacio_id=:u'),{'u':user})
            for user in users:
                c.execute(text('DELETE FROM public.espacios WHERE id=:u'),{'u':user});c.execute(text('DELETE FROM public.perfiles WHERE usuario_id=:u'),{'u':user})
        runtime.dispose();migrator.dispose()
