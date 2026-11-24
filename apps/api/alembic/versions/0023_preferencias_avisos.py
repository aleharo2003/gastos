"""Preferencias personales de recordatorios para cada espacio."""
from alembic import op
import sqlalchemy as sa

revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'preferencias_avisos',
        sa.Column('usuario_id', sa.Uuid(), nullable=False),
        sa.Column('espacio_id', sa.Uuid(), nullable=False),
        sa.Column('canal', sa.Text(), nullable=False),
        sa.Column('dias_anticipacion', sa.Integer(), nullable=False),
        sa.Column('hora_local', sa.Time(), nullable=False),
        sa.Column('vencimientos', sa.Boolean(), nullable=False),
        sa.Column('vencidas', sa.Boolean(), nullable=False),
        sa.Column('resumen_semanal', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('usuario_id', 'espacio_id', name='pk_preferencias_avisos'),
        sa.ForeignKeyConstraint(
            ['usuario_id', 'espacio_id'],
            ['public.miembros_espacio.usuario_id', 'public.miembros_espacio.espacio_id'],
            name='fk_preferencias_avisos_miembro', ondelete='CASCADE',
        ),
        sa.CheckConstraint("canal IN ('ninguno', 'email', 'push')", name='ck_preferencias_avisos_canal'),
        sa.CheckConstraint("dias_anticipacion BETWEEN 0 AND 30", name='ck_preferencias_avisos_anticipacion'),
        sa.CheckConstraint("hora_local < TIME '24:00' AND EXTRACT(SECOND FROM hora_local) = 0", name='ck_preferencias_avisos_hora'),
        schema='public',
    )
    table = 'public.preferencias_avisos'
    op.execute(f'REVOKE ALL ON {table} FROM PUBLIC, anon, authenticated, service_role, app_runtime')
    op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY preferencias_avisos_migrator ON {table} TO app_migrator USING (true) WITH CHECK (true)')
    self_context = """
        usuario_id = NULLIF(current_setting('app.user_id', true), '')::uuid
        AND espacio_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid
    """
    op.execute(f'CREATE POLICY preferencias_avisos_personal ON {table} TO app_runtime '
               f'USING ({self_context}) WITH CHECK ({self_context})')
    op.execute(f'GRANT SELECT, INSERT ON {table} TO app_runtime')
    op.execute(f'GRANT UPDATE (canal, dias_anticipacion, hora_local, vencimientos, vencidas, resumen_semanal) ON {table} TO app_runtime')


def downgrade():
    op.execute("""DO $check$ BEGIN
        IF EXISTS (SELECT 1 FROM public.preferencias_avisos)
        THEN RAISE EXCEPTION 'Hay preferencias guardadas; conservarlas antes de revertir la migración.';
        END IF;
        END $check$""")
    op.drop_table('preferencias_avisos', schema='public')
