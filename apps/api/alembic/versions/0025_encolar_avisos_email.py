"""Registra avisos elegibles una sola vez por fecha local."""
from alembic import op
import sqlalchemy as sa

revision = '0025'
down_revision = '0024'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'avisos_email',
        sa.Column('usuario_id', sa.Uuid(), nullable=False),
        sa.Column('espacio_id', sa.Uuid(), nullable=False),
        sa.Column('cuota_id', sa.Uuid(), nullable=False),
        sa.Column('evento', sa.Text(), nullable=False),
        sa.Column('fecha_aviso', sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint(
            'usuario_id', 'espacio_id', 'cuota_id', 'evento', 'fecha_aviso', name='pk_avisos_email',
        ),
        sa.ForeignKeyConstraint(
            ['usuario_id', 'espacio_id'],
            ['public.miembros_espacio.usuario_id', 'public.miembros_espacio.espacio_id'],
            name='fk_avisos_email_miembro', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['espacio_id', 'cuota_id'],
            ['public.cuotas.espacio_id', 'public.cuotas.id'],
            name='fk_avisos_email_cuota', ondelete='CASCADE',
        ),
        sa.CheckConstraint("evento IN ('vencimiento', 'vencida')", name='ck_avisos_email_evento'),
        schema='public',
    )
    op.execute('REVOKE ALL ON public.avisos_email FROM PUBLIC, anon, authenticated, service_role, app_runtime')
    op.execute('ALTER TABLE public.avisos_email ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE public.avisos_email FORCE ROW LEVEL SECURITY')
    op.execute("""CREATE POLICY avisos_email_migrator ON public.avisos_email
        TO app_migrator USING (true) WITH CHECK (true)""")
    op.execute("""
        CREATE FUNCTION public.encolar_avisos_email(instante timestamptz) RETURNS bigint
        LANGUAGE sql VOLATILE STRICT SET search_path = pg_catalog AS $fn$
            WITH nuevos AS (
                INSERT INTO public.avisos_email (usuario_id, espacio_id, cuota_id, evento, fecha_aviso)
                SELECT usuario_id, espacio_id, cuota_id, evento, fecha_aviso
                FROM public.candidatos_avisos_email(instante)
                ORDER BY usuario_id, espacio_id, cuota_id, evento, fecha_aviso
                ON CONFLICT (usuario_id, espacio_id, cuota_id, evento, fecha_aviso) DO NOTHING
                RETURNING 1
            )
            SELECT count(*) FROM nuevos
        $fn$
    """)
    op.execute("""
        REVOKE ALL ON FUNCTION public.encolar_avisos_email(timestamptz)
        FROM PUBLIC, anon, authenticated, service_role, app_runtime
    """)


def downgrade():
    op.execute("""DO $check$ BEGIN
        IF EXISTS (SELECT 1 FROM public.avisos_email)
        THEN RAISE EXCEPTION 'Hay avisos registrados; conservarlos antes de revertir la migración.';
        END IF;
        END $check$""")
    op.execute('DROP FUNCTION public.encolar_avisos_email(timestamptz)')
    op.drop_table('avisos_email', schema='public')
