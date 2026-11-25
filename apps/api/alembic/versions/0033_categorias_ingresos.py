"""Categoría opcional para ingresos."""
from alembic import op
import sqlalchemy as sa

revision = '0033'
down_revision = '0032'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('ingresos', sa.Column('categoria', sa.Text()), schema='public')
    op.create_check_constraint('ck_ingresos_categoria', 'ingresos',
                               "categoria IS NULL OR categoria ~ '^[a-z0-9_-]{1,36}$'", schema='public')


def downgrade() -> None:
    op.drop_constraint('ck_ingresos_categoria', 'ingresos', type_='check', schema='public')
    op.drop_column('ingresos', 'categoria', schema='public')
