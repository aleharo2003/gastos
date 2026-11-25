"""Conservar los límites por categoría al cierre de cada mes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0038'
down_revision = '0037'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('planes_gasto', sa.Column(
        'historial_categoria', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb"),
    ), schema='public')
    op.create_check_constraint('ck_planes_gasto_historial_categoria', 'planes_gasto',
                               "jsonb_typeof(historial_categoria) = 'object'", schema='public')
    op.execute("""
        UPDATE public.planes_gasto
        SET historial_categoria = jsonb_build_object(
            to_char(statement_timestamp() AT TIME ZONE 'America/Argentina/Buenos_Aires', 'YYYY-MM'),
            COALESCE(datos->'limites_categoria', '[]'::jsonb)
        )
    """)
    op.execute('REVOKE INSERT ON public.planes_gasto FROM app_runtime')
    op.execute('GRANT INSERT (espacio_id, version, datos) ON public.planes_gasto TO app_runtime')
    op.execute("""
        CREATE FUNCTION public.registrar_limites_categoria_del_mes() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $body$
        BEGIN
            IF TG_OP = 'INSERT' AND NEW.historial_categoria <> '{}'::jsonb THEN
                RETURN NEW;
            END IF;
            NEW.historial_categoria := NEW.historial_categoria || jsonb_build_object(
                to_char(statement_timestamp() AT TIME ZONE 'America/Argentina/Buenos_Aires', 'YYYY-MM'),
                COALESCE(NEW.datos->'limites_categoria', '[]'::jsonb)
            );
            RETURN NEW;
        END;
        $body$
    """)
    op.execute("""
        REVOKE ALL ON FUNCTION public.registrar_limites_categoria_del_mes()
        FROM PUBLIC, anon, authenticated, service_role, app_runtime
    """)
    op.execute("""
        CREATE TRIGGER registrar_limites_categoria_del_mes BEFORE INSERT OR UPDATE OF datos
        ON public.planes_gasto FOR EACH ROW EXECUTE FUNCTION public.registrar_limites_categoria_del_mes()
    """)


def downgrade():
    op.execute('DROP TRIGGER registrar_limites_categoria_del_mes ON public.planes_gasto')
    op.execute('DROP FUNCTION public.registrar_limites_categoria_del_mes()')
    op.drop_constraint('ck_planes_gasto_historial_categoria', 'planes_gasto', schema='public')
    op.drop_column('planes_gasto', 'historial_categoria', schema='public')
    op.execute('REVOKE INSERT (espacio_id, version, datos) ON public.planes_gasto FROM app_runtime')
    op.execute('GRANT INSERT ON public.planes_gasto TO app_runtime')
