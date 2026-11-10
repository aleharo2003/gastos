"""Categoria opcional: conserva gastos y comprobantes existentes."""
from alembic import op
import sqlalchemy as sa

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('gastos', sa.Column('categoria',sa.Text(),nullable=True),schema='public')
    op.create_check_constraint('ck_gastos_categoria','gastos',"categoria IS NULL OR categoria IN ('alimentos','transporte','vivienda','servicios','salud','educacion','ocio','impuestos','auto','bancario','ropa','otros')",schema='public')
    op.execute('GRANT UPDATE (categoria) ON public.gastos TO app_runtime')

def downgrade():
    op.execute('REVOKE UPDATE (categoria) ON public.gastos FROM app_runtime')
    op.drop_constraint('ck_gastos_categoria','gastos',schema='public',type_='check')
    op.drop_column('gastos','categoria',schema='public')
