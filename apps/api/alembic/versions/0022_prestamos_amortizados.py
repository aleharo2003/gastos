"""Persiste las condiciones y el desglose del calendario de préstamos."""
import sqlalchemy as sa
from alembic import op

revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('compromisos', sa.Column('sistema_amortizacion', sa.Text()), schema='public')
    op.add_column('compromisos', sa.Column('tna', sa.Numeric(26, 8)), schema='public')
    op.create_check_constraint(
        'ck_compromisos_amortizacion', 'compromisos',
        "(sistema_amortizacion IS NULL AND tna IS NULL) OR ("
        "sistema_amortizacion IS NOT NULL AND sistema_amortizacion IN ('frances','aleman') "
        "AND tna IS NOT NULL AND tna >= 0 AND tna < 1000000000000000000 "
        "AND indice_ajuste IS NULL AND total_cuotas IS NOT NULL AND NOT variable)",
        schema='public',
    )
    for field in ('capital', 'interes', 'saldo_capital'):
        op.add_column('cuotas', sa.Column(field, sa.Numeric(14, 2)), schema='public')
    op.create_check_constraint(
        'ck_cuotas_amortizacion', 'cuotas',
        '(capital IS NULL AND interes IS NULL AND saldo_capital IS NULL) OR ('
        'capital IS NOT NULL AND interes IS NOT NULL AND saldo_capital IS NOT NULL AND '
        'capital > 0 AND interes >= 0 AND saldo_capital >= 0 AND importe = capital + interes '
        'AND NOT no_aplica AND NOT estimado AND NOT pendiente_ajuste)',
        schema='public',
    )


def downgrade():
    op.execute("""DO $check$ BEGIN
        IF EXISTS (SELECT 1 FROM public.compromisos WHERE sistema_amortizacion IS NOT NULL)
        THEN RAISE EXCEPTION 'Hay préstamos amortizados; conservar el desglose antes de revertir.';
        END IF;
        END $check$""")
    op.drop_constraint('ck_cuotas_amortizacion', 'cuotas', type_='check', schema='public')
    for field in ('saldo_capital', 'interes', 'capital'):
        op.drop_column('cuotas', field, schema='public')
    op.drop_constraint('ck_compromisos_amortizacion', 'compromisos', type_='check', schema='public')
    op.drop_column('compromisos', 'tna', schema='public')
    op.drop_column('compromisos', 'sistema_amortizacion', schema='public')
