"""Variaciones mensuales de indices, aisladas por espacio."""
from alembic import op
import sqlalchemy as sa

revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'variaciones_indice',
        sa.Column('espacio_id', sa.Uuid(), nullable=False),
        sa.Column('indice', sa.Text(), nullable=False),
        sa.Column('periodo', sa.Date(), nullable=False),
        sa.Column('variacion', sa.Numeric(10, 4), nullable=False),
        sa.PrimaryKeyConstraint('espacio_id', 'indice', 'periodo', name='pk_variaciones_indice'),
        sa.ForeignKeyConstraint(
            ['espacio_id'], ['public.espacios.id'], ondelete='CASCADE',
            name='fk_variaciones_indice_espacio_id_espacios',
        ),
        sa.CheckConstraint("length(btrim(indice)) BETWEEN 1 AND 80", name='ck_variaciones_indice_nombre'),
        sa.CheckConstraint(
            "periodo BETWEEN DATE '0001-01-01' AND DATE '9999-12-01' AND EXTRACT(DAY FROM periodo) = 1",
            name='ck_variaciones_indice_periodo',
        ),
        sa.CheckConstraint(
            "variacion > -100 AND variacion <= 999999.9999", name='ck_variaciones_indice_variacion',
        ),
        schema='public',
    )
    table = 'public.variaciones_indice'
    op.execute(f'REVOKE ALL ON {table} FROM PUBLIC, anon, authenticated, service_role, app_runtime')
    op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY variaciones_indice_migrator ON {table} TO app_migrator USING (true) WITH CHECK (true)')
    member = """
        espacio_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid
        AND EXISTS (
            SELECT 1 FROM public.miembros_espacio m
            WHERE m.espacio_id = variaciones_indice.espacio_id
              AND m.usuario_id = NULLIF(current_setting('app.user_id', true), '')::uuid
              AND m.rol IN ({roles})
        )
    """
    read = member.format(roles="'owner', 'editor', 'lector'")
    write = member.format(roles="'owner', 'editor'")
    op.execute(f'CREATE POLICY variaciones_indice_read ON {table} FOR SELECT TO app_runtime USING ({read})')
    op.execute(f'CREATE POLICY variaciones_indice_insert ON {table} FOR INSERT TO app_runtime WITH CHECK ({write})')
    op.execute(f'GRANT SELECT, INSERT ON {table} TO app_runtime')


def downgrade():
    op.drop_table('variaciones_indice', schema='public')
