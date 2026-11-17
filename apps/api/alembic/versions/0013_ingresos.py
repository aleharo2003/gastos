"""Ingresos por cuenta y moneda, con aislamiento y precision decimal."""
from alembic import op
import sqlalchemy as sa
revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('ingresos',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('espacio_id', sa.Uuid(), nullable=False),
        sa.Column('cuenta_id', sa.Uuid(), nullable=False),
        sa.Column('usuario_id', sa.Uuid(), nullable=False),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=False),
        sa.Column('moneda', sa.Text(), nullable=False),
        sa.Column('importe', sa.Numeric(14, 2), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_ingresos'),
        sa.ForeignKeyConstraint(['espacio_id','cuenta_id'], ['public.cuentas.espacio_id','public.cuentas.id'],
                                name='fk_ingresos_espacio_id_cuenta_id_cuentas'),
        sa.ForeignKeyConstraint(['usuario_id'], ['public.perfiles.usuario_id'], name='fk_ingresos_usuario_id_perfiles'),
        sa.CheckConstraint("moneda IN ('ARS','USD','EUR')", name='ck_ingresos_moneda'),
        sa.CheckConstraint('importe > 0 AND importe < 1000000000000', name='ck_ingresos_importe'),
        sa.CheckConstraint('char_length(btrim(descripcion)) BETWEEN 1 AND 160', name='ck_ingresos_descripcion'),
        schema='public')
    op.create_index('ix_ingresos_espacio_cuenta_fecha','ingresos',['espacio_id','cuenta_id','fecha'],schema='public')
    op.execute('REVOKE ALL ON public.ingresos FROM PUBLIC, anon, authenticated, service_role, app_runtime')
    op.execute('ALTER TABLE public.ingresos ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE public.ingresos FORCE ROW LEVEL SECURITY')
    op.execute('CREATE POLICY ingresos_migrator ON public.ingresos FOR ALL TO app_migrator USING (true) WITH CHECK (true)')
    member = """
        espacio_id = nullif(current_setting('app.workspace_id', true), '')::uuid
        AND EXISTS (
            SELECT 1 FROM public.miembros_espacio m
            WHERE m.espacio_id = ingresos.espacio_id
              AND m.usuario_id = nullif(current_setting('app.user_id', true), '')::uuid
              AND m.rol IN ({roles})
        )
    """
    read = member.format(roles="'owner','editor','lector'")
    write = member.format(roles="'owner','editor'")
    op.execute(f'CREATE POLICY ingresos_lectura ON public.ingresos FOR SELECT TO app_runtime USING ({read})')
    op.execute(f"""CREATE POLICY ingresos_insercion ON public.ingresos FOR INSERT TO app_runtime
        WITH CHECK ({write} AND usuario_id = nullif(current_setting('app.user_id', true), '')::uuid)""")
    op.execute('GRANT SELECT, INSERT ON public.ingresos TO app_runtime')


def downgrade():
    op.drop_table('ingresos', schema='public')
