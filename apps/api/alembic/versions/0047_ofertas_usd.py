"""Ofertas de USD agrupadas por ronda."""
from alembic import op
import sqlalchemy as sa

revision = '0047'
down_revision = '0046'
branch_labels = None
depends_on = None


def upgrade():
    table = 'public.ofertas_usd'
    op.create_unique_constraint('uq_ventas_usd_espacio_id', 'ventas_usd', ['espacio_id','id'], schema='public')
    op.create_table('ofertas_usd',
        sa.Column('espacio_id', sa.Uuid(), sa.ForeignKey('public.espacios.id', ondelete='CASCADE'), nullable=False),
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('ronda', sa.Uuid(), nullable=False),
        sa.Column('contraparte', sa.Text(), nullable=False),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('tasa', sa.Numeric(12,4), nullable=False),
        sa.Column('referencia', sa.Numeric(12,4)),
        sa.Column('fecha_referencia', sa.Date()),
        sa.Column('estado', sa.Text(), nullable=False, server_default='vigente'),
        sa.Column('venta_id', sa.Uuid(), unique=True),
        sa.ForeignKeyConstraint(['espacio_id','venta_id'], ['public.ventas_usd.espacio_id','public.ventas_usd.id'],
                                name='fk_ofertas_usd_espacio_venta'),
        sa.CheckConstraint("tasa > 0 AND tasa < 100000000 AND length(btrim(contraparte)) BETWEEN 1 AND 160", name='ck_ofertas_usd_datos'),
        sa.CheckConstraint("estado IN ('vigente','aceptada','rechazada') AND (estado='aceptada') = (venta_id IS NOT NULL)", name='ck_ofertas_usd_estado'),
        schema='public')
    op.create_index('ix_ofertas_usd_espacio_ronda', 'ofertas_usd', ['espacio_id','ronda'], schema='public')
    op.create_index('uq_ofertas_usd_aceptada', 'ofertas_usd', ['espacio_id','ronda'], unique=True,
                    schema='public', postgresql_where=sa.text("estado='aceptada'"))
    op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY ofertas_migrator ON {table} TO app_migrator USING (true) WITH CHECK (true)')
    scope = """espacio_id=NULLIF(current_setting('app.workspace_id',true),'')::uuid
        AND EXISTS (SELECT FROM public.miembros_espacio m WHERE m.espacio_id=ofertas_usd.espacio_id
            AND m.usuario_id=NULLIF(current_setting('app.user_id',true),'')::uuid {role})"""
    reader = scope.format(role='')
    writer = scope.format(role="AND m.rol IN ('owner','editor')")
    op.execute(f'CREATE POLICY ofertas_read ON {table} FOR SELECT TO app_runtime USING ({reader})')
    op.execute(f"CREATE POLICY ofertas_insert ON {table} FOR INSERT TO app_runtime WITH CHECK ({writer} AND estado='vigente')")
    op.execute(f"""CREATE POLICY ofertas_update ON {table} FOR UPDATE TO app_runtime
        USING ({writer} AND estado='vigente')
        WITH CHECK ({writer} AND estado IN ('aceptada','rechazada')
            AND (venta_id IS NULL OR EXISTS (SELECT FROM public.ventas_usd v
                WHERE v.espacio_id=ofertas_usd.espacio_id AND v.id=ofertas_usd.venta_id)))""")
    op.execute(f'REVOKE ALL ON {table} FROM PUBLIC, anon, authenticated, service_role, app_runtime')
    op.execute(f'GRANT SELECT, INSERT ON {table} TO app_runtime')
    op.execute(f'GRANT UPDATE (estado, venta_id) ON {table} TO app_runtime')
    op.execute("""
        DO $backup$ BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname='app_backup'
                       AND has_table_privilege(oid, 'public.espacios', 'SELECT')) THEN
                CREATE POLICY respaldo_lectura ON public.ofertas_usd FOR SELECT TO app_backup
                    USING (EXISTS (SELECT FROM public.espacios e WHERE e.id=ofertas_usd.espacio_id));
                GRANT SELECT ON public.ofertas_usd TO app_backup;
            END IF;
        END $backup$;
    """)


def downgrade():
    op.drop_table('ofertas_usd', schema='public')
    op.drop_constraint('uq_ventas_usd_espacio_id', 'ventas_usd', schema='public', type_='unique')
