"""Copias cifradas y restauración de datos PostgreSQL de un espacio de Piggo."""
from datetime import UTC, datetime
from decimal import Decimal
import gzip
from io import BytesIO
import json
import os
from pathlib import Path
import sys
from uuid import UUID

from cryptography.fernet import Fernet
from psycopg import connect, sql

FORMAT = 'piggo-postgresql-v1'
MAX_BYTES = 64 * 1024 * 1024
# Orden válido para reconstruir claves foráneas. Las tablas nuevas requieren decisión explícita.
TABLES = (
    'perfiles', 'espacios', 'miembros_espacio', 'cuentas', 'categorias_movimientos',
    'variaciones_indice', 'compromisos', 'cuotas', 'ingresos', 'gastos', 'transferencias',
    'pagos_cuota', 'metas_ahorro', 'planes_gasto', 'comprobantes', 'preferencias_avisos', 'gastos_pendientes',
    'cotizaciones_manuales', 'preferencias_cotizacion', 'ventas_usd',
)


def tables_for(revisions):
    head = max(revisions, default='')
    introduced = {'gastos_pendientes': '0040', 'cotizaciones_manuales': '0044', 'preferencias_cotizacion': '0045', 'ventas_usd': '0046'}
    return tuple(table for table in TABLES if table not in introduced or head >= introduced[table])


def snapshot(connection, space: UUID) -> bytes:
    """Leer una instantánea estable con un rol de solo lectura y alcance fijo."""
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        cursor.execute("""
            SELECT current_user='app_backup' AND session_user=current_user
                AND NOT (rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication OR rolinherit)
                AND NOT EXISTS (SELECT FROM pg_auth_members WHERE member=pg_roles.oid)
            FROM pg_roles WHERE rolname=current_user
        """)
        if cursor.fetchone() != (True,):
            raise ValueError('Se requiere el rol app_backup')
        cursor.execute('SELECT version_num FROM public.alembic_version')  # Acceso concedido a este identificador técnico.
        revisions = sorted(row[0] for row in cursor)
        cursor.execute('SELECT id FROM public.espacios')
        if cursor.fetchall() != [(space,)]:
            raise ValueError('El rol debe poder leer solamente el espacio configurado')
        header = {
            'format': FORMAT, 'space': str(space), 'revisions': revisions,
            'created_at': datetime.now(UTC).isoformat(),
        }
        content = BytesIO()

        def write(value: str) -> None:
            data = value.encode('utf-8')
            if content.tell() + len(data) > MAX_BYTES:
                raise ValueError('El respaldo supera el límite de tamaño')
            content.write(data)

        write(json.dumps(header)[:-1] + ',"tables":{')
        for index, table in enumerate(tables_for(revisions)):
            write((',' if index else '') + json.dumps(table) + ':[')
            # Cursor del servidor: el límite no depende de materializar la tabla completa.
            with connection.cursor(name='piggo_backup_rows') as rows:
                rows.execute(sql.SQL('SELECT to_jsonb(t)::text FROM public.{} AS t').format(sql.Identifier(table)))
                for position, (document,) in enumerate(rows):
                    write((',' if position else '') + document)
            write(']')
        write('}}')
        return content.getvalue()


def encrypt_archive(data: bytes, key: str) -> bytes:
    return Fernet(key).encrypt(gzip.compress(data))


def decrypt_archive(token: bytes, key: str) -> bytes:
    with gzip.GzipFile(fileobj=BytesIO(Fernet(key).decrypt(token))) as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('El respaldo excede el tamaño permitido')
    return data


def restore(connection, data: bytes) -> None:
    """Restaurar solo en una base vacía con las mismas revisiones de esquema."""
    archive = json.loads(data, parse_float=Decimal)
    expected_tables = tables_for(archive['revisions'])
    if archive['format'] != FORMAT or set(archive['tables']) != set(expected_tables):
        raise ValueError('Formato de respaldo incompatible')
    space = str(UUID(archive['space']))
    tables = archive['tables']
    if len(tables['espacios']) != 1 or tables['espacios'][0]['id'] != space:
        raise ValueError('El archivo debe contener un solo espacio')
    if any(row['espacio_id'] != space for table in expected_tables if table not in ('espacios', 'perfiles')
           for row in tables[table]):
        raise ValueError('El archivo mezcla datos de espacios distintos')

    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute('SELECT version_num FROM public.alembic_version')
        if sorted(row[0] for row in cursor) != archive['revisions']:
            raise ValueError('La revisión de PostgreSQL no coincide con el respaldo')
        cursor.execute('LOCK TABLE public.espacios IN EXCLUSIVE MODE')
        cursor.execute('SELECT EXISTS (SELECT FROM public.espacios) OR EXISTS (SELECT FROM public.perfiles)')
        if cursor.fetchone() != (False,):
            raise ValueError('Usá una base vacía y desechable para restaurar')
        # PostgreSQL interpreta el JSON original y conserva numéricos y ACL de las filas.
        raw = data.decode('utf-8')
        for table in expected_tables:
            cursor.execute("""
                SELECT attname FROM pg_attribute
                WHERE attrelid=to_regclass(%s) AND attnum>0 AND NOT attisdropped AND attgenerated=''
                ORDER BY attnum
            """, ('public.' + table,))
            names = [row[0] for row in cursor]
            columns = sql.SQL(', ').join(map(sql.Identifier, names))
            values = sql.SQL(', ').join(sql.SQL('true') if table == 'cuentas' and name == 'activa'
                                        else sql.Identifier(name) for name in names)
            identifier = sql.Identifier('public', table)
            cursor.execute(sql.SQL("""
                INSERT INTO {} ({}) SELECT {} FROM jsonb_populate_recordset(NULL::{}, %s::jsonb->'tables'->%s)
            """).format(identifier, columns, values, identifier), (raw, table))
            if cursor.rowcount != len(tables[table]):
                raise ValueError('La cantidad de filas restauradas no coincide')
        # Los triggers de registro nuevo requieren cuentas activas. Restaurar su estado histórico al final.
        cursor.execute("""
            UPDATE public.cuentas AS c SET activa=r.activa
            FROM jsonb_populate_recordset(NULL::public.cuentas, %s::jsonb->'tables'->'cuentas') AS r
            WHERE c.espacio_id=%s AND c.id=r.id AND c.activa IS DISTINCT FROM r.activa
        """, (raw, space))


def main(args: list[str]) -> None:
    mode, filename = args
    path = Path(filename)
    key = os.environ['PIGGO_BACKUP_KEY']
    if mode == 'snapshot':
        with connect(os.environ['PIGGO_BACKUP_DATABASE_URL'], sslmode='verify-full', connect_timeout=10,
                     options='-c statement_timeout=60000') as connection:
            data = snapshot(connection, UUID(os.environ['PIGGO_BACKUP_SPACE_ID']))
        archive = encrypt_archive(data, key)
        with path.open('xb') as output:
            output.write(archive)
    elif mode == 'restore':
        from psycopg.conninfo import conninfo_to_dict
        dsn = os.environ['PIGGO_RESTORE_DATABASE_URL']
        settings = conninfo_to_dict(dsn)
        if settings.get('host') not in ('127.0.0.1', '::1') or 'hostaddr' in settings:
            raise ValueError('La restauración solo admite una base local desechable')
        with path.open('rb') as source:
            token = source.read(MAX_BYTES * 2 + 1)
        if len(token) > MAX_BYTES * 2:
            raise ValueError('El archivo excede el tamaño permitido')
        data = decrypt_archive(token, key)
        with connect(dsn, connect_timeout=10) as connection:
            restore(connection, data)
    else:
        raise ValueError('Operación desconocida')


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except Exception as failure:
        print(f'Falló el resguardo o la restauración ({type(failure).__name__}).', file=sys.stderr)
        sys.exit(1)
