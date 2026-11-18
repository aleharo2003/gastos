"""Devuelve los avisos encolados que todavía corresponden al momento de prepararlos."""
from alembic import op

revision = '0026'
down_revision = '0025'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE FUNCTION public.avisos_email_para_preparar(instante timestamptz)
        RETURNS TABLE (
            usuario_id uuid, espacio_id uuid, cuota_id uuid, fecha_aviso date,
            evento text, vencimiento date, nombre text, numero integer, moneda text,
            pendiente numeric, estimado boolean, pendiente_ajuste boolean
        )
        LANGUAGE sql STABLE STRICT SET search_path = pg_catalog AS $fn$
            SELECT actual.*
            FROM public.candidatos_avisos_email(instante) actual
            JOIN public.avisos_email registrado USING (
                usuario_id, espacio_id, cuota_id, evento, fecha_aviso
            )
        $fn$
    """)
    op.execute("""
        REVOKE ALL ON FUNCTION public.avisos_email_para_preparar(timestamptz)
        FROM PUBLIC, anon, authenticated, service_role, app_runtime
    """)


def downgrade():
    op.execute('DROP FUNCTION public.avisos_email_para_preparar(timestamptz)')
