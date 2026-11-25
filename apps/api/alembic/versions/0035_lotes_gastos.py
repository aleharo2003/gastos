"""Vincular gastos importados a un lote y conservar sus claves de origen."""
from alembic import op
import sqlalchemy as sa

revision = '0035'
down_revision = '0034'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('gastos', sa.Column('lote_importacion', sa.Uuid()), schema='public')
    op.add_column('gastos', sa.Column('clave_importacion', sa.Uuid()), schema='public')
    op.add_column('gastos', sa.Column('importado_en', sa.DateTime(timezone=True)), schema='public')
    op.create_index('ix_gastos_espacio_lote', 'gastos', ['espacio_id', 'lote_importacion'],
                    schema='public', postgresql_where=sa.text('lote_importacion IS NOT NULL'))
    op.create_index('uq_gastos_importacion_vigente', 'gastos', ['espacio_id', 'clave_importacion'], unique=True,
                    schema='public', postgresql_where=sa.text('clave_importacion IS NOT NULL AND anulado_en IS NULL'))


def downgrade():
    op.drop_index('uq_gastos_importacion_vigente', table_name='gastos', schema='public')
    op.drop_index('ix_gastos_espacio_lote', table_name='gastos', schema='public')
    op.drop_column('gastos', 'importado_en', schema='public')
    op.drop_column('gastos', 'clave_importacion', schema='public')
    op.drop_column('gastos', 'lote_importacion', schema='public')
