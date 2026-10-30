"""Audita FKs por espacio y demuestra el contrato con una tabla de prueba transitoria.

No implementa movimientos ni sustituye sus pruebas futuras.
"""
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.connection import create_migration_engine


class WorkspaceLinkError(RuntimeError):
    pass


def assert_workspace_links(connection):
    # Solo relaciones existentes: no detecta una FK omitida por completo.
    invalid = connection.execute(text("""
        SELECT k.conname
        FROM pg_constraint k
        JOIN pg_class child ON child.oid=k.conrelid
        JOIN pg_namespace n ON n.oid=child.relnamespace
        JOIN pg_attribute a ON a.attrelid=k.conrelid
          AND a.attname='espacio_id' AND NOT a.attisdropped
        JOIN pg_attribute b ON b.attrelid=k.confrelid
          AND b.attname='espacio_id' AND NOT b.attisdropped
        WHERE k.contype='f'
          AND n.nspname='public'
          AND NOT (a.attnotnull AND b.attnotnull
            AND a.attnum=ANY(k.conkey)
            AND b.attnum=k.confkey[array_position(k.conkey, a.attnum)]
            AND k.convalidated)
        ORDER BY k.conname
    """)).scalars().all()
    if invalid:
        raise WorkspaceLinkError('FK sin aislamiento por espacio: ' + ','.join(invalid))


def check_workspace_links(migration_url):
    engine = create_migration_engine(migration_url)
    try:
        with engine.connect() as c:
            tx = c.begin()
            try:
                assert_workspace_links(c)
                sa, sb, ca, cb = (uuid4() for _ in range(4))
                c.execute(text('INSERT INTO public.espacios (id,nombre) VALUES (:id,:n)'),
                          [{'id':sa,'n':'Contrato FK A'}, {'id':sb,'n':'Contrato FK B'}])
                c.execute(text('INSERT INTO public.cuentas (id,espacio_id,nombre) VALUES (:id,:s,:n)'),
                          [{'id':ca,'s':sa,'n':'Contrato A'}, {'id':cb,'s':sb,'n':'Contrato B'}])
                c.execute(text('''CREATE TABLE public.gastos_ci_workspace_link (
                    id uuid PRIMARY KEY,
                    espacio_id uuid NOT NULL,
                    cuenta_id uuid NOT NULL,
                    CONSTRAINT fk_ci_workspace_account FOREIGN KEY (espacio_id,cuenta_id)
                      REFERENCES public.cuentas(espacio_id,id)
                )'''))
                assert_workspace_links(c)
                insert = text('INSERT INTO public.gastos_ci_workspace_link VALUES (:id,:s,:a)')
                row_a, row_b = uuid4(), uuid4()
                c.execute(insert,[{'id':row_a,'s':sa,'a':ca}, {'id':row_b,'s':sb,'a':cb}])

                def rejected(sql, params):
                    try:
                        with c.begin_nested():
                            c.execute(sql, params)
                    except DBAPIError as error:
                        if (getattr(error.orig,'sqlstate',None) != '23503'
                                or error.orig.diag.constraint_name != 'fk_ci_workspace_account'):
                            raise WorkspaceLinkError('La prueba fallo por otra causa') from error
                    else:
                        raise WorkspaceLinkError('Se admitio una relacion entre espacios distintos')

                rejected(insert, {'id':uuid4(),'s':sa,'a':cb})
                rejected(insert, {'id':uuid4(),'s':sb,'a':ca})
                rejected(text('UPDATE public.gastos_ci_workspace_link SET cuenta_id=:a WHERE id=:id'),
                         {'id':row_a,'a':cb})
                rejected(text('UPDATE public.gastos_ci_workspace_link SET espacio_id=:s WHERE id=:id'),
                         {'id':row_a,'s':sb})
                # Contraprueba: solo cuenta_id garantiza existencia, no el espacio.
                savepoint = c.begin_nested()
                try:
                    c.execute(text('ALTER TABLE public.gastos_ci_workspace_link DROP CONSTRAINT fk_ci_workspace_account'))
                    c.execute(text('ALTER TABLE public.gastos_ci_workspace_link ADD CONSTRAINT fk_ci_weak_account FOREIGN KEY (cuenta_id) REFERENCES public.cuentas(id)'))
                    try:
                        assert_workspace_links(c)
                    except WorkspaceLinkError as error:
                        if str(error) != 'FK sin aislamiento por espacio: fk_ci_weak_account':
                            raise
                    else:
                        raise WorkspaceLinkError('El auditor no detecto la FK incompleta')
                    c.execute(insert, {'id':uuid4(),'s':sa,'a':cb})
                finally:
                    savepoint.rollback()
                assert_workspace_links(c)
                rejected(insert, {'id':uuid4(),'s':sa,'a':cb})
                rows = set(c.execute(text('SELECT espacio_id,cuenta_id FROM public.gastos_ci_workspace_link')).all())
                if rows != {(sa,ca),(sb,cb)}:
                    raise WorkspaceLinkError('Las operaciones rechazadas modificaron los datos')
            finally:
                tx.rollback()
            with c.begin():
                if c.execute(text("SELECT to_regclass('public.gastos_ci_workspace_link')")).scalar_one() is not None:
                    raise WorkspaceLinkError('La tabla de prueba no se retiro')
                assert_workspace_links(c)
    finally:
        engine.dispose()
    print('OK: auditoria de FKs por espacio y contrato temporal; FK simple detectada y enlace cruzado rechazado.', flush=True)
