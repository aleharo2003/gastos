"""Reserva y resuelve intentos para cada correo diario."""
from alembic import op
import sqlalchemy as sa

revision = '0027'
down_revision = '0026'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'entregas_avisos_email',
        sa.Column('usuario_id', sa.Uuid(), nullable=False),
        sa.Column('espacio_id', sa.Uuid(), nullable=False),
        sa.Column('fecha_aviso', sa.Date(), nullable=False),
        sa.Column('intento_id', sa.Uuid(), nullable=False),
        sa.Column('reservado_en', sa.DateTime(timezone=True), nullable=False),
        sa.Column('estado', sa.Text(), nullable=False),
        sa.Column('referencia_proveedor', sa.Text()),
        sa.PrimaryKeyConstraint('usuario_id', 'espacio_id', 'fecha_aviso', name='pk_entregas_avisos_email'),
        sa.ForeignKeyConstraint(
            ['usuario_id', 'espacio_id'],
            ['public.miembros_espacio.usuario_id', 'public.miembros_espacio.espacio_id'],
            name='fk_entregas_avisos_email_miembro', ondelete='CASCADE',
        ),
        sa.UniqueConstraint('intento_id', name='uq_entregas_avisos_email_intento'),
        sa.CheckConstraint("estado IN ('reservada', 'aceptada', 'reintento', 'incierta')", name='ck_entregas_avisos_email_estado'),
        sa.CheckConstraint("(estado = 'aceptada' AND referencia_proveedor IS NOT NULL AND char_length(btrim(referencia_proveedor)) BETWEEN 1 AND 255) OR (estado <> 'aceptada' AND referencia_proveedor IS NULL)", name='ck_entregas_avisos_email_referencia'),
        schema='public',
    )
    table = 'public.entregas_avisos_email'
    op.execute(f'REVOKE ALL ON {table} FROM PUBLIC, anon, authenticated, service_role, app_runtime')
    op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY entregas_avisos_email_migrator ON {table} TO app_migrator USING (true) WITH CHECK (true)')
    op.execute("""
        CREATE FUNCTION public.reservar_entrega_aviso_email(destinatario uuid, espacio uuid, instante timestamptz)
        RETURNS uuid LANGUAGE sql VOLATILE STRICT SET search_path = pg_catalog AS $fn$
            INSERT INTO public.entregas_avisos_email AS entrega
                (usuario_id, espacio_id, fecha_aviso, intento_id, reservado_en, estado)
            SELECT destinatario, espacio,
                   (instante AT TIME ZONE 'America/Argentina/Buenos_Aires')::date,
                   gen_random_uuid(), clock_timestamp(), 'reservada'
            WHERE EXISTS (
                SELECT 1 FROM public.avisos_email_para_preparar(instante) actual
                WHERE actual.usuario_id = destinatario AND actual.espacio_id = espacio
            )
            ON CONFLICT (usuario_id, espacio_id, fecha_aviso) DO UPDATE SET
                intento_id = EXCLUDED.intento_id, reservado_en = EXCLUDED.reservado_en, estado = 'reservada'
            WHERE entrega.estado = 'reintento'
            RETURNING intento_id
        $fn$
    """)
    op.execute("""
        CREATE FUNCTION public.resolver_entrega_aviso_email(intento uuid, resultado text, referencia text)
        RETURNS boolean LANGUAGE sql VOLATILE SET search_path = pg_catalog AS $fn$
            WITH cambios AS (
                UPDATE public.entregas_avisos_email
                SET estado = resultado, referencia_proveedor = referencia
                WHERE intento_id = intento AND estado = 'reservada'
                  AND (
                      (resultado = 'aceptada' AND char_length(btrim(referencia)) BETWEEN 1 AND 255)
                      OR (resultado IN ('reintento', 'incierta') AND referencia IS NULL)
                  )
                RETURNING 1
            )
            SELECT EXISTS (SELECT 1 FROM cambios)
        $fn$
    """)
    for signature in (
        'reservar_entrega_aviso_email(uuid,uuid,timestamptz)',
        'resolver_entrega_aviso_email(uuid,text,text)',
    ):
        op.execute(f'REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC, anon, authenticated, service_role, app_runtime')


def downgrade():
    op.execute("""DO $check$ BEGIN
        IF EXISTS (SELECT 1 FROM public.entregas_avisos_email)
        THEN RAISE EXCEPTION 'Hay intentos de entrega registrados; conservarlos antes de revertir la migración.';
        END IF;
        END $check$""")
    op.execute('DROP FUNCTION public.resolver_entrega_aviso_email(uuid,text,text)')
    op.execute('DROP FUNCTION public.reservar_entrega_aviso_email(uuid,uuid,timestamptz)')
    op.drop_table('entregas_avisos_email', schema='public')
