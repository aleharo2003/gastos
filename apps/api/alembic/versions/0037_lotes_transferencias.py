"""Identificar y anular transferencias importados en lote."""
from alembic import op
import sqlalchemy as sa

revision = '0037'
down_revision = '0036'
branch_labels = None
depends_on = None

COLUMNS = (
    ('lote_importacion', sa.Uuid()),
    ('clave_importacion', sa.Uuid()),
    ('importado_en', sa.DateTime(timezone=True)),
    ('anulado_en', sa.DateTime(timezone=True)),
)


def upgrade():
    for name, kind in COLUMNS:
        op.add_column('transferencias', sa.Column(name, kind), schema='public')
    op.create_index('ix_transferencias_espacio_lote', 'transferencias', ['espacio_id', 'lote_importacion'],
                    schema='public', postgresql_where=sa.text('lote_importacion IS NOT NULL'))
    op.create_index('uq_transferencias_importacion_vigente', 'transferencias', ['espacio_id', 'clave_importacion'],
                    unique=True, schema='public',
                    postgresql_where=sa.text('clave_importacion IS NOT NULL AND anulado_en IS NULL'))
    editor = """
        lote_importacion IS NOT NULL
        AND espacio_id = nullif(current_setting('app.workspace_id', true), '')::uuid
        AND EXISTS (
            SELECT 1 FROM public.miembros_espacio m
            WHERE m.espacio_id = transferencias.espacio_id
              AND m.usuario_id = nullif(current_setting('app.user_id', true), '')::uuid
              AND m.rol IN ('owner','editor')
        )
    """
    op.execute(f"""CREATE POLICY transferencias_anular_importados ON public.transferencias FOR UPDATE TO app_runtime
        USING ({editor} AND anulado_en IS NULL) WITH CHECK ({editor} AND anulado_en IS NOT NULL)""")
    op.execute('GRANT UPDATE (anulado_en) ON public.transferencias TO app_runtime')


def downgrade():
    op.execute('REVOKE UPDATE (anulado_en) ON public.transferencias FROM app_runtime')
    op.execute('DROP POLICY transferencias_anular_importados ON public.transferencias')
    op.drop_index('uq_transferencias_importacion_vigente', table_name='transferencias', schema='public')
    op.drop_index('ix_transferencias_espacio_lote', table_name='transferencias', schema='public')
    for name, _ in reversed(COLUMNS):
        op.drop_column('transferencias', name, schema='public')
