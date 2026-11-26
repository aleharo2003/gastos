"""Generacion independiente: una funcion permitida, sin arrancar API ni BFF."""
import os
import sys
import psycopg


def verify_jobs_role(cursor):
    cursor.execute("""SELECT session_user,current_user,rolsuper,rolbypassrls,rolcreatedb,
        rolcreaterole,rolreplication,rolinherit,
        (SELECT count(*) FROM pg_auth_members WHERE member=r.oid)
        FROM pg_roles r WHERE rolname=current_user""")
    if cursor.fetchone()!=('app_jobs','app_jobs',False,False,False,False,False,False,0):
        raise RuntimeError('La conexion no cumple el contrato de app_jobs.')


def generate(connector=psycopg.connect):
    dsn=os.environ.get('JOBS_DATABASE_URL','')
    if not dsn:raise RuntimeError('Falta configurar JOBS_DATABASE_URL.')
    with connector(dsn,connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            verify_jobs_role(cursor)
            cursor.execute("SET LOCAL statement_timeout='120s'")
            cursor.execute("SET LOCAL lock_timeout='30s'")
            cursor.execute('SELECT public.generar_cuotas_mes()')
            count=cursor.fetchone()[0]
            if not isinstance(count,int) or count<0:raise RuntimeError('Respuesta de generacion invalida.')
    return count


def main():
    try:
        count=generate()
        print(f'OK: generacion mensual confirmada; cuotas creadas={count}.')
        return 0
    except Exception:
        # Nunca volcar DSN, traceback ni errores que puedan incluir credenciales.
        print('ERROR: no se confirmo la generacion mensual. Revisar conexion app_jobs, migracion 0017 y permisos.',file=sys.stderr)
        return 1


if __name__=='__main__':sys.exit(main())
