"""Prueba el rol habilitado, el archivo cifrado y su restauración en Supabase desechable."""
from decimal import Decimal
import json
from pathlib import Path
import sys
from uuid import uuid4

from cryptography.fernet import Fernet
from psycopg import connect
from psycopg.errors import InsufficientPrivilege

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'jobs'))
from backup_space import decrypt_archive, encrypt_archive, restore, snapshot


def check_backup(migration_url, password, grant_path):
    owner, other, account, expense = (uuid4() for _ in range(4))
    conninfo = dict(host=migration_url.host, port=migration_url.port, dbname=migration_url.database)
    migrator = conninfo | dict(user=migration_url.username, password=migration_url.password)
    reader = conninfo | dict(user='app_backup', password=password)
    with connect(**migrator) as connection:
        for user in (owner, other):
            connection.execute('INSERT INTO public.perfiles VALUES (%s,%s)', (user, 'Fixture'))
            connection.execute('INSERT INTO public.espacios VALUES (%s,%s)', (user, 'Fixture'))
            connection.execute("INSERT INTO public.miembros_espacio VALUES (%s,%s,'owner')", (user, user))
        connection.execute("INSERT INTO public.cuentas(id,espacio_id,nombre) VALUES (%s,%s,'Banco')", (account, owner))
        connection.execute("""
            INSERT INTO public.gastos(id,espacio_id,cuenta_id,usuario_id,fecha,descripcion,moneda,importe,nota)
            VALUES (%s,%s,%s,%s,'2026-11-01','=1+1','ARS',98765.43,'Prueba de restauración')
        """, (expense, owner, account, owner))
        connection.execute('UPDATE public.cuentas SET activa=false WHERE id=%s', (account,))
        connection.execute("SELECT set_config('piggo.backup_space', %s, true)", (str(owner),))
        body = grant_path.read_text(encoding='utf-8').split('DO $grant$', 1)[1].rsplit('COMMIT;', 1)[0]
        connection.execute('DO $grant$' + body)

    with connect(**reader) as connection:
        payload = snapshot(connection, owner)
        assert [row['usuario_id'] for row in json.loads(payload)['tables']['perfiles']] == [str(owner)]
        with connection.transaction():
            connection.execute("SELECT set_config('piggo.backup_space', %s, true)", (str(other),))
            assert connection.execute('SELECT id FROM public.espacios').fetchall() == [(owner,)]
        try:
            with connection.transaction():
                connection.execute("UPDATE public.cuentas SET activa=true")
        except InsufficientPrivilege:
            pass
        else:
            raise AssertionError('El rol de resguardo pudo modificar datos')

    key = Fernet.generate_key()
    archive = encrypt_archive(payload, key)
    assert b'Prueba de restauraci' not in archive
    data = decrypt_archive(archive, key)
    assert data == payload
    # Solo se vacían las filas sintéticas de esta prueba, en la fixture desechable.
    def remove_test_rows(connection):
        connection.execute('DELETE FROM public.gastos WHERE id=%s', (expense,))
        connection.execute('DELETE FROM public.cuentas WHERE id=%s', (account,))
        connection.execute('DELETE FROM public.miembros_espacio WHERE espacio_id IN (%s,%s)', (owner, other))
        connection.execute('DELETE FROM public.espacios WHERE id IN (%s,%s)', (owner, other))
        connection.execute('DELETE FROM public.perfiles WHERE usuario_id IN (%s,%s)', (owner, other))

    with connect(**migrator) as connection:
        remove_test_rows(connection)
        restore(connection, data)
        assert connection.execute('SELECT importe,descripcion,nota FROM public.gastos WHERE id=%s', (expense,)).fetchone() == (
            Decimal('98765.43'), '=1+1', 'Prueba de restauración')
        assert connection.execute('SELECT activa FROM public.cuentas WHERE id=%s', (account,)).fetchone() == (False,)
        assert connection.execute('SELECT id FROM public.espacios').fetchall() == [(owner,)]
        remove_test_rows(connection)
    print('OK: una sola cuenta de respaldo, una sola área de datos, cifrado y restauración en PostgreSQL desechable.')
