"""Objetos futuros cerrados hasta conceder permisos explícitos."""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    if connection.execute(sa.text('SELECT current_user')).scalar_one() != 'app_migrator':
        raise RuntimeError('Ejecutar esta migracion como app_migrator.')
    # Global elimina también EXECUTE de PUBLIC, que no puede retirarse
    # solamente con IN SCHEMA. Ambos ámbitos pertenecen a nuestro creador.
    for scope in ('', 'IN SCHEMA public'):
        for kind in ('TABLES', 'SEQUENCES', 'FUNCTIONS'):
            op.execute(f'ALTER DEFAULT PRIVILEGES FOR ROLE app_migrator {scope} '
                       f'REVOKE ALL ON {kind} FROM PUBLIC, anon, authenticated, service_role, app_runtime')
    # Solo objetos propios: nunca REVOKE ... ON ALL ... IN SCHEMA public,
    # que podría alcanzar objetos de extensiones o de Supabase.
    op.execute("""
        DO $hardening$
        DECLARE obj record;
        BEGIN
          FOR obj IN
            SELECT c.relname, c.relkind FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relowner=current_user::regrole
              AND c.relkind IN ('r','p','v','m','f','S')
          LOOP
            EXECUTE format('REVOKE ALL ON %s public.%I FROM PUBLIC, anon, authenticated, service_role',
              CASE WHEN obj.relkind='S' THEN 'SEQUENCE' ELSE 'TABLE' END, obj.relname);
          END LOOP;
          FOR obj IN
            SELECT p.oid::regprocedure AS signature FROM pg_proc p
            JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname='public' AND p.proowner=current_user::regrole
          LOOP
            EXECUTE format('REVOKE ALL ON ROUTINE %s FROM PUBLIC, anon, authenticated, service_role', obj.signature);
          END LOOP;
        END
        $hardening$;
    """)


def downgrade():
    raise RuntimeError('0006 no restaura grants anteriores desconocidos. Crear una migracion correctiva revisada.')
