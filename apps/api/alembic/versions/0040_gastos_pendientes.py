"""Registrar obligaciones sin movimiento de dinero hasta pagarlas."""
from alembic import op
import sqlalchemy as sa

revision = '0040'
down_revision = '0039'
branch_labels = None
depends_on = None


def upgrade():
    table = 'gastos_pendientes'
    op.create_table(
        table,
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('espacio_id', sa.Uuid(), nullable=False),
        sa.Column('cuenta_id', sa.Uuid(), nullable=False),
        sa.Column('usuario_id', sa.Uuid(), sa.ForeignKey('public.perfiles.usuario_id'), nullable=False),
        sa.Column('fecha_devengamiento', sa.Date()),
        sa.Column('fecha_vencimiento', sa.Date(), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=False),
        sa.Column('moneda', sa.Text(), nullable=False),
        sa.Column('importe', sa.Numeric(14, 2), nullable=False),
        sa.Column('categoria', sa.Text()),
        sa.Column('nota', sa.Text()),
        sa.Column('gasto_id', sa.Uuid()),
        sa.ForeignKeyConstraint(['espacio_id', 'cuenta_id'], ['public.cuentas.espacio_id', 'public.cuentas.id']),
        sa.ForeignKeyConstraint(['espacio_id', 'gasto_id'], ['public.gastos.espacio_id', 'public.gastos.id']),
        sa.CheckConstraint('gasto_id IS NULL OR gasto_id=id', name='ck_gastos_pendientes_pago'),
        sa.CheckConstraint("moneda IN ('ARS','USD','EUR')", name='ck_gastos_pendientes_moneda'),
        sa.CheckConstraint('importe > 0 AND importe < 1000000000000', name='ck_gastos_pendientes_importe'),
        sa.CheckConstraint('char_length(btrim(descripcion)) BETWEEN 1 AND 160', name='ck_gastos_pendientes_descripcion'),
        sa.CheckConstraint('nota IS NULL OR char_length(nota) BETWEEN 1 AND 500', name='ck_gastos_pendientes_nota'),
        schema='public',
    )
    op.create_index('ix_gastos_pendientes_espacio_vencimiento', table, ['espacio_id', 'fecha_vencimiento', 'id'],
                    schema='public', postgresql_where=sa.text('gasto_id IS NULL'))
    relation = 'public.gastos_pendientes'
    member = """espacio_id=NULLIF(current_setting('app.workspace_id',true),'')::uuid
      AND EXISTS (SELECT 1 FROM public.miembros_espacio m
        WHERE m.espacio_id=gastos_pendientes.espacio_id
          AND m.usuario_id=NULLIF(current_setting('app.user_id',true),'')::uuid {role})"""
    writer = member.format(role="AND m.rol IN ('owner','editor')")
    op.execute(f'ALTER TABLE {relation} ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE {relation} FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY gastos_pendientes_migrator ON {relation} TO app_migrator USING (true) WITH CHECK (true)')
    op.execute(f"CREATE POLICY gastos_pendientes_read ON {relation} FOR SELECT TO app_runtime USING ({member.format(role='')})")
    op.execute(f"""CREATE POLICY gastos_pendientes_insert ON {relation} FOR INSERT TO app_runtime
        WITH CHECK ({writer} AND gasto_id IS NULL AND usuario_id=NULLIF(current_setting('app.user_id',true),'')::uuid)""")
    op.execute(f"""CREATE POLICY gastos_pendientes_pay ON {relation} FOR UPDATE TO app_runtime
        USING ({writer} AND gasto_id IS NULL) WITH CHECK ({writer} AND gasto_id=id)""")
    op.execute(f'REVOKE ALL ON {relation} FROM PUBLIC, anon, authenticated, service_role')
    op.execute(f'GRANT SELECT, INSERT ON {relation} TO app_runtime')
    op.execute(f'GRANT UPDATE (gasto_id) ON {relation} TO app_runtime')
    op.execute("""
        DO $backup$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='app_backup'
                       AND has_table_privilege(oid, 'public.espacios', 'SELECT')) THEN
                CREATE POLICY respaldo_lectura ON public.gastos_pendientes FOR SELECT TO app_backup
                    USING (EXISTS (SELECT 1 FROM public.espacios e WHERE e.id=gastos_pendientes.espacio_id));
                GRANT SELECT ON public.gastos_pendientes TO app_backup;
            END IF;
        END;
        $backup$
    """)


def downgrade():
    op.drop_table('gastos_pendientes', schema='public')
