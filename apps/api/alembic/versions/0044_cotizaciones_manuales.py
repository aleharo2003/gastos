"""Cotizaciones manuales de USD, compartidas por espacio y fecha."""
from alembic import op
import sqlalchemy as sa

revision = '0044'
down_revision = '0043'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cotizaciones_manuales',
        sa.Column('espacio_id', sa.Uuid(), sa.ForeignKey('public.espacios.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('fecha', sa.Date(), primary_key=True),
        sa.Column('tasa', sa.Numeric(12, 4), nullable=False),
        sa.CheckConstraint('tasa > 0 AND tasa < 100000000', name='ck_cotizaciones_manuales_tasa'),
        schema='public',
    )
    table = 'public.cotizaciones_manuales'
    member = """
        espacio_id=NULLIF(current_setting('app.workspace_id', true),'')::uuid
        AND EXISTS (SELECT 1 FROM public.miembros_espacio m
            WHERE m.espacio_id=cotizaciones_manuales.espacio_id
              AND m.usuario_id=NULLIF(current_setting('app.user_id', true),'')::uuid {role})
    """
    reader = member.format(role='')
    writer = member.format(role="AND m.rol IN ('owner','editor')")
    op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY cotizaciones_migrator ON {table} TO app_migrator USING (true) WITH CHECK (true)')
    op.execute(f'CREATE POLICY cotizaciones_read ON {table} FOR SELECT TO app_runtime USING ({reader})')
    op.execute(f'CREATE POLICY cotizaciones_insert ON {table} FOR INSERT TO app_runtime WITH CHECK ({writer})')
    op.execute(f'CREATE POLICY cotizaciones_update ON {table} FOR UPDATE TO app_runtime USING ({writer}) WITH CHECK ({writer})')
    op.execute(f'REVOKE ALL ON {table} FROM PUBLIC, anon, authenticated, service_role')
    op.execute(f'GRANT SELECT, INSERT ON {table} TO app_runtime')
    op.execute(f'GRANT UPDATE (tasa) ON {table} TO app_runtime')
    op.execute("""
        DO $backup$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname='app_backup'
                       AND has_table_privilege(oid, 'public.espacios', 'SELECT')) THEN
                CREATE POLICY respaldo_lectura ON public.cotizaciones_manuales FOR SELECT TO app_backup
                    USING (EXISTS (SELECT FROM public.espacios e WHERE e.id=cotizaciones_manuales.espacio_id));
                GRANT SELECT ON public.cotizaciones_manuales TO app_backup;
            END IF;
        END
        $backup$
    """)


def downgrade():
    op.drop_table('cotizaciones_manuales', schema='public')
