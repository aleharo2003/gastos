"""Ventas de USD con dos importes exactos y cotización de la operación."""
from alembic import op
import sqlalchemy as sa

revision = '0046'
down_revision = '0045'
branch_labels = None
depends_on = None


def upgrade():
    table = 'public.ventas_usd'
    op.create_table('ventas_usd',
        sa.Column('espacio_id', sa.Uuid(), nullable=False),
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('origen_id', sa.Uuid(), nullable=False),
        sa.Column('destino_id', sa.Uuid(), nullable=False),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('contraparte', sa.Text(), nullable=False),
        sa.Column('usd', sa.Numeric(14, 2), nullable=False),
        sa.Column('ars', sa.Numeric(14, 2), nullable=False),
        sa.Column('tasa', sa.Numeric(), sa.Computed('round(ars / NULLIF(usd,0), 4)', persisted=True)),
        sa.Column('referencia', sa.Numeric(12, 4)),
        sa.Column('fecha_referencia', sa.Date()),
        sa.ForeignKeyConstraint(['espacio_id','origen_id'], ['public.cuentas.espacio_id','public.cuentas.id'], name='fk_ventas_usd_origen_cuentas'),
        sa.ForeignKeyConstraint(['espacio_id','destino_id'], ['public.cuentas.espacio_id','public.cuentas.id'], name='fk_ventas_usd_destino_cuentas'),
        sa.CheckConstraint('origen_id<>destino_id AND usd>0 AND usd<1000000000000 AND ars>0 AND ars<1000000000000', name='ck_ventas_montos'),
        sa.CheckConstraint('length(btrim(contraparte)) BETWEEN 1 AND 160', name='ck_ventas_contraparte'),
        sa.CheckConstraint('(referencia IS NULL AND fecha_referencia IS NULL) OR (referencia > 0 AND fecha_referencia <= fecha AND fecha_referencia IS NOT NULL)', name='ck_ventas_referencia'),
        schema='public')
    op.create_index('ix_ventas_usd_espacio_fecha', 'ventas_usd', ['espacio_id', 'fecha', 'id'], schema='public')
    op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY ventas_migrator ON {table} TO app_migrator USING (true) WITH CHECK (true)')
    scope = """espacio_id=NULLIF(current_setting('app.workspace_id',true),'')::uuid
        AND EXISTS (SELECT FROM public.miembros_espacio m WHERE m.espacio_id=ventas_usd.espacio_id
            AND m.usuario_id=NULLIF(current_setting('app.user_id',true),'')::uuid {role})"""
    reader = scope.format(role='')
    writer = scope.format(role="AND m.rol IN ('owner','editor')")
    op.execute(f'CREATE POLICY ventas_read ON {table} FOR SELECT TO app_runtime USING ({reader})')
    op.execute(f"""CREATE POLICY ventas_insert ON {table} FOR INSERT TO app_runtime WITH CHECK ({writer}
        AND EXISTS (SELECT FROM public.cuentas c WHERE c.espacio_id=ventas_usd.espacio_id
          AND c.id=ventas_usd.origen_id AND c.activa AND (c.moneda IS NULL OR c.moneda='USD'))
        AND EXISTS (SELECT FROM public.cuentas c WHERE c.espacio_id=ventas_usd.espacio_id
          AND c.id=ventas_usd.destino_id AND c.activa AND (c.moneda IS NULL OR c.moneda='ARS')))""")
    op.execute(f'REVOKE ALL ON {table} FROM PUBLIC, anon, authenticated, service_role, app_runtime')
    op.execute(f'GRANT SELECT, INSERT ON {table} TO app_runtime')
    op.execute("""
        DO $backup$ BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname='app_backup'
                       AND has_table_privilege(oid, 'public.espacios', 'SELECT')) THEN
                CREATE POLICY respaldo_lectura ON public.ventas_usd FOR SELECT TO app_backup
                    USING (EXISTS (SELECT FROM public.espacios e WHERE e.id=ventas_usd.espacio_id));
                GRANT SELECT ON public.ventas_usd TO app_backup;
            END IF;
        END $backup$;
    """)


def downgrade():
    op.drop_table('ventas_usd', schema='public')
