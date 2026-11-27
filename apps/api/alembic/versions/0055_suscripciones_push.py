"""Suscripciones Web Push privadas por dispositivo."""
from alembic import op
import sqlalchemy as sa

revision = '0055'
down_revision = '0054'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'suscripciones_push',
        sa.Column('usuario_id', sa.Uuid(), primary_key=True),
        sa.Column('espacio_id', sa.Uuid(), primary_key=True),
        sa.Column('dispositivo_id', sa.Uuid(), primary_key=True),
        sa.Column('endpoint', sa.Text(), nullable=False),
        sa.Column('p256dh', sa.Text(), nullable=False),
        sa.Column('auth', sa.Text(), nullable=False),
        sa.UniqueConstraint('endpoint', name='uq_suscripciones_push_endpoint'),
        sa.ForeignKeyConstraint(['usuario_id', 'espacio_id'],
                                ['public.miembros_espacio.usuario_id', 'public.miembros_espacio.espacio_id'],
                                name='fk_suscripciones_push_miembro', ondelete='CASCADE'),
        schema='public',
    )
    table = 'public.suscripciones_push'
    op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY suscripciones_push_migrator ON {table} TO app_migrator USING (true) WITH CHECK (true)')
    scope = """usuario_id=nullif(current_setting('app.user_id',true),'')::uuid
          AND espacio_id=nullif(current_setting('app.workspace_id',true),'')::uuid
          AND EXISTS (SELECT FROM public.miembros_espacio m WHERE
              m.usuario_id=suscripciones_push.usuario_id AND m.espacio_id=suscripciones_push.espacio_id)"""
    op.execute(f'CREATE POLICY suscripciones_push_personal ON {table} TO app_runtime USING ({scope}) WITH CHECK ({scope})')
    op.execute(f'REVOKE ALL ON {table} FROM PUBLIC, anon, authenticated, service_role, app_runtime')
    op.execute(f'GRANT SELECT, INSERT, DELETE ON {table} TO app_runtime')
    op.execute(f'GRANT UPDATE (endpoint, p256dh, auth) ON {table} TO app_runtime')


def downgrade():
    op.drop_table('suscripciones_push', schema='public')
