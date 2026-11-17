"""Transferencias atomicas entre cuentas de la misma moneda, con aislamiento y precision decimal."""
from alembic import op
import sqlalchemy as sa
revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('transferencias',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('espacio_id', sa.Uuid(), nullable=False),
        sa.Column('origen_id', sa.Uuid(), nullable=False),
        sa.Column('destino_id', sa.Uuid(), nullable=False),
        sa.Column('usuario_id', sa.Uuid(), nullable=False),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=False),
        sa.Column('moneda', sa.Text(), nullable=False),
        sa.Column('importe', sa.Numeric(14, 2), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_transferencias'),
        sa.ForeignKeyConstraint(['espacio_id','origen_id'], ['public.cuentas.espacio_id','public.cuentas.id'],
                                name='fk_transferencias_espacio_id_origen_id_cuentas'),
        sa.ForeignKeyConstraint(['espacio_id','destino_id'], ['public.cuentas.espacio_id','public.cuentas.id'],
                                name='fk_transferencias_espacio_id_destino_id_cuentas'),
        sa.CheckConstraint('origen_id <> destino_id', name='ck_transferencias_cuentas_distintas'),
        sa.ForeignKeyConstraint(['usuario_id'], ['public.perfiles.usuario_id'], name='fk_transferencias_usuario_id_perfiles'),
        sa.CheckConstraint("moneda IN ('ARS','USD','EUR')", name='ck_transferencias_moneda'),
        sa.CheckConstraint('importe > 0 AND importe < 1000000000000', name='ck_transferencias_importe'),
        sa.CheckConstraint('char_length(btrim(descripcion)) BETWEEN 1 AND 160', name='ck_transferencias_descripcion'),
        schema='public')
    op.create_index('ix_transferencias_espacio_origen_fecha','transferencias',['espacio_id','origen_id','fecha'],schema='public')
    op.create_index('ix_transferencias_espacio_destino_fecha','transferencias',['espacio_id','destino_id','fecha'],schema='public')
    op.execute('REVOKE ALL ON public.transferencias FROM PUBLIC, anon, authenticated, service_role, app_runtime')
    op.execute('ALTER TABLE public.transferencias ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE public.transferencias FORCE ROW LEVEL SECURITY')
    op.execute('CREATE POLICY transferencias_migrator ON public.transferencias FOR ALL TO app_migrator USING (true) WITH CHECK (true)')
    member = """
        espacio_id = nullif(current_setting('app.workspace_id', true), '')::uuid
        AND EXISTS (
            SELECT 1 FROM public.miembros_espacio m
            WHERE m.espacio_id = transferencias.espacio_id
              AND m.usuario_id = nullif(current_setting('app.user_id', true), '')::uuid
              AND m.rol IN ({roles})
        )
    """
    read = member.format(roles="'owner','editor','lector'")
    write = member.format(roles="'owner','editor'")
    op.execute(f'CREATE POLICY transferencias_lectura ON public.transferencias FOR SELECT TO app_runtime USING ({read})')
    op.execute(f"""CREATE POLICY transferencias_insercion ON public.transferencias FOR INSERT TO app_runtime
        WITH CHECK ({write} AND usuario_id = nullif(current_setting('app.user_id', true), '')::uuid)""")
    op.execute('GRANT SELECT, INSERT ON public.transferencias TO app_runtime')


def downgrade():
    op.drop_table('transferencias', schema='public')
