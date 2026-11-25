"""Índices por espacio y fecha para el historial unificado."""
from alembic import op

revision = '0034'
down_revision = '0033'
branch_labels = None
depends_on = None

TABLES = ('gastos', 'ingresos', 'transferencias')


def upgrade() -> None:
    for table in TABLES:
        op.create_index(f'ix_{table}_espacio_fecha', table, ['espacio_id', 'fecha'], schema='public')


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_index(f'ix_{table}_espacio_fecha', table_name=table, schema='public')
