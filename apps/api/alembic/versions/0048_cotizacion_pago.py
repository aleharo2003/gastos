"""Cotización de los pagos en USD."""
from alembic import op
import sqlalchemy as sa

revision = '0048'
down_revision = '0047'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('ventas_usd', sa.Column('registrada_en', sa.DateTime(timezone=True)), schema='public')
    op.alter_column('ventas_usd', 'registrada_en', server_default=sa.func.now(), schema='public')
    op.add_column('gastos', sa.Column('tasa_pago', sa.Numeric(20,4)), schema='public')
    op.add_column('gastos', sa.Column('fuente_tasa_pago', sa.Text()), schema='public')
    op.create_check_constraint('ck_gastos_tasa_pago', 'gastos', """
        (tasa_pago IS NULL AND fuente_tasa_pago IS NULL)
        OR (moneda='USD' AND tasa_pago IS NOT NULL AND tasa_pago > 0 AND tasa_pago <> 'NaN'::numeric
            AND fuente_tasa_pago IS NOT NULL AND fuente_tasa_pago IN ('referencia','ultima_venta','manual'))
    """, schema='public')


def downgrade():
    op.drop_constraint('ck_gastos_tasa_pago', 'gastos', schema='public', type_='check')
    op.drop_column('gastos', 'fuente_tasa_pago', schema='public')
    op.drop_column('gastos', 'tasa_pago', schema='public')
    op.drop_column('ventas_usd', 'registrada_en', schema='public')
