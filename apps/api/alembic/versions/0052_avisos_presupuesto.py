"""Preferencia privada y avisos deduplicados por período de presupuesto."""
from alembic import op
import sqlalchemy as sa

revision = '0052'
down_revision = '0051'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('preferencias_avisos', sa.Column('exceso_presupuesto', sa.Boolean(), nullable=False,
                                                  server_default='false'), schema='public')
    op.execute('GRANT UPDATE (exceso_presupuesto) ON public.preferencias_avisos TO app_runtime')
    op.create_table(
        'avisos_presupuesto',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('usuario_id', sa.Uuid(), nullable=False),
        sa.Column('espacio_id', sa.Uuid(), nullable=False),
        sa.Column('periodo', sa.Text(), nullable=False),
        sa.Column('desde', sa.Date(), nullable=False),
        sa.Column('categoria', sa.Text(), nullable=False),
        sa.Column('moneda', sa.Text(), nullable=False),
        sa.Column('exceso', sa.Numeric(), nullable=False),
        sa.Column('leida', sa.Boolean(), nullable=False, server_default='false'),
        sa.ForeignKeyConstraint(['usuario_id', 'espacio_id'],
                                ['public.miembros_espacio.usuario_id', 'public.miembros_espacio.espacio_id'],
                                name='fk_avisos_presupuesto_miembro', ondelete='CASCADE'),
        sa.UniqueConstraint('usuario_id', 'espacio_id', 'periodo', 'desde', 'categoria',
                            name='uq_avisos_presupuesto_periodo'),
        sa.CheckConstraint("periodo IN ('diario','semanal','mensual') AND moneda IN ('ARS','USD') AND exceso>0",
                           name='ck_avisos_presupuesto_datos'),
        schema='public',
    )
    table = 'public.avisos_presupuesto'
    op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY avisos_presupuesto_migrator ON {table} TO app_migrator USING (true) WITH CHECK (true)')
    scope = """usuario_id=nullif(current_setting('app.user_id',true),'')::uuid
        AND espacio_id=nullif(current_setting('app.workspace_id',true),'')::uuid
        AND EXISTS (SELECT FROM public.miembros_espacio m
                    WHERE m.espacio_id=avisos_presupuesto.espacio_id AND m.usuario_id=avisos_presupuesto.usuario_id)"""
    op.execute(f'CREATE POLICY avisos_presupuesto_personal ON {table} TO app_runtime USING ({scope}) WITH CHECK ({scope})')
    op.execute(f'REVOKE ALL ON {table} FROM PUBLIC, anon, authenticated, service_role, app_runtime')
    op.execute(f'GRANT SELECT, INSERT ON {table} TO app_runtime')
    op.execute(f'GRANT UPDATE (leida) ON {table} TO app_runtime')


def downgrade():
    op.drop_table('avisos_presupuesto', schema='public')
    op.drop_column('preferencias_avisos', 'exceso_presupuesto', schema='public')
