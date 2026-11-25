"""Identificar y anular ingresos importados en lote."""
from alembic import op
import sqlalchemy as sa

revision = '0036'
down_revision = '0035'
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
        op.add_column('ingresos', sa.Column(name, kind), schema='public')
    op.create_index('ix_ingresos_espacio_lote', 'ingresos', ['espacio_id', 'lote_importacion'],
                    schema='public', postgresql_where=sa.text('lote_importacion IS NOT NULL'))
    op.create_index('uq_ingresos_importacion_vigente', 'ingresos', ['espacio_id', 'clave_importacion'],
                    unique=True, schema='public',
                    postgresql_where=sa.text('clave_importacion IS NOT NULL AND anulado_en IS NULL'))
    editor = """
        lote_importacion IS NOT NULL
        AND espacio_id = nullif(current_setting('app.workspace_id', true), '')::uuid
        AND EXISTS (
            SELECT 1 FROM public.miembros_espacio m
            WHERE m.espacio_id = ingresos.espacio_id
              AND m.usuario_id = nullif(current_setting('app.user_id', true), '')::uuid
              AND m.rol IN ('owner','editor')
        )
    """
    op.execute(f"""CREATE POLICY ingresos_anular_importados ON public.ingresos FOR UPDATE TO app_runtime
        USING ({editor} AND anulado_en IS NULL) WITH CHECK ({editor} AND anulado_en IS NOT NULL)""")
    op.execute('GRANT UPDATE (anulado_en) ON public.ingresos TO app_runtime')


def downgrade():
    op.execute('REVOKE UPDATE (anulado_en) ON public.ingresos FROM app_runtime')
    op.execute('DROP POLICY ingresos_anular_importados ON public.ingresos')
    op.drop_index('uq_ingresos_importacion_vigente', table_name='ingresos', schema='public')
    op.drop_index('ix_ingresos_espacio_lote', table_name='ingresos', schema='public')
    for name, _ in reversed(COLUMNS):
        op.drop_column('ingresos', name, schema='public')
