"""Conservar los gastos anulados para auditoría."""
from alembic import op
import sqlalchemy as sa

revision = '0031'
down_revision = '0030'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('gastos', sa.Column('anulado_en', sa.DateTime(timezone=True)), schema='public')
    op.execute('GRANT UPDATE (anulado_en) ON TABLE public.gastos TO app_runtime')


def downgrade() -> None:
    op.drop_column('gastos', 'anulado_en', schema='public')
