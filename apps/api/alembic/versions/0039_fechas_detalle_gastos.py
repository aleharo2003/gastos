"""Guardar devengamiento y vencimiento de los gastos pagados."""
from alembic import op
import sqlalchemy as sa

revision = '0039'
down_revision = '0038'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('gastos', sa.Column('fecha_devengamiento', sa.Date()), schema='public')
    op.add_column('gastos', sa.Column('fecha_vencimiento', sa.Date()), schema='public')
    op.execute('GRANT UPDATE (fecha_devengamiento, fecha_vencimiento) ON public.gastos TO app_runtime')


def downgrade():
    op.drop_column('gastos', 'fecha_vencimiento', schema='public')
    op.drop_column('gastos', 'fecha_devengamiento', schema='public')
