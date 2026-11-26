"""Datos de alta de cuentas y saldo inicial separado de los movimientos."""
from alembic import op
import sqlalchemy as sa

revision = '0042'
down_revision = '0041'
branch_labels = None
depends_on = None

COLUMNS = (
    ('tipo', sa.Text()),
    ('moneda', sa.String(3)),
    ('saldo_inicial', sa.Numeric(14, 2)),
    ('dia_cierre', sa.SmallInteger()),
    ('dia_vencimiento', sa.SmallInteger()),
    ('fecha_vencimiento', sa.Date()),
    ('tasa_anual', sa.Numeric(7, 4)),
)


def upgrade():
    for name, kind in COLUMNS:
        op.add_column('cuentas', sa.Column(name, kind), schema='public')
    op.create_check_constraint('ck_cuentas_datos', 'cuentas', """
        CASE WHEN tipo IS NULL THEN
            moneda IS NULL AND saldo_inicial IS NULL AND dia_cierre IS NULL
            AND dia_vencimiento IS NULL AND fecha_vencimiento IS NULL AND tasa_anual IS NULL
        ELSE
            tipo IN ('efectivo', 'banco', 'tarjeta_credito', 'billetera', 'inversion')
            AND moneda IS NOT NULL AND moneda IN ('ARS', 'USD', 'EUR')
            AND saldo_inicial IS NOT NULL AND saldo_inicial <> 'NaN'::numeric
            AND CASE WHEN tipo = 'tarjeta_credito'
                THEN dia_cierre IS NOT NULL AND dia_cierre BETWEEN 1 AND 31
                     AND dia_vencimiento IS NOT NULL AND dia_vencimiento BETWEEN 1 AND 31
                ELSE dia_cierre IS NULL AND dia_vencimiento IS NULL END
            AND CASE WHEN tipo = 'inversion'
                THEN fecha_vencimiento IS NOT NULL AND tasa_anual IS NOT NULL
                     AND tasa_anual >= 0 AND tasa_anual <> 'NaN'::numeric AND saldo_inicial > 0
                ELSE fecha_vencimiento IS NULL AND tasa_anual IS NULL END
        END
    """, schema='public')


def downgrade():
    op.drop_constraint('ck_cuentas_datos', 'cuentas', schema='public', type_='check')
    for name, _ in reversed(COLUMNS):
        op.drop_column('cuentas', name, schema='public')
