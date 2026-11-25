"""Nota opcional en gastos."""
from alembic import op
import sqlalchemy as sa

revision = '0030'
down_revision = '0029'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('gastos', sa.Column('nota', sa.Text()), schema='public')
    op.create_check_constraint('ck_gastos_nota', 'gastos',
                               'nota IS NULL OR char_length(nota) BETWEEN 1 AND 500', schema='public')
    op.execute('GRANT UPDATE (nota) ON TABLE public.gastos TO app_runtime')


def downgrade() -> None:
    op.drop_constraint('ck_gastos_nota', 'gastos', type_='check', schema='public')
    op.drop_column('gastos', 'nota', schema='public')
