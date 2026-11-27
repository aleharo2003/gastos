"""Permite anular ingresos y transferencias individuales."""
from alembic import op

revision = '0050'
down_revision = '0049'
branch_labels = None
depends_on = None


def set_policies(imported_only):
    for table in ('ingresos', 'transferencias'):
        imported = 'lote_importacion IS NOT NULL AND' if imported_only else ''
        editor = f"""
            {imported}
            espacio_id = nullif(current_setting('app.workspace_id', true), '')::uuid
            AND EXISTS (
                SELECT 1 FROM public.miembros_espacio m
                WHERE m.espacio_id = {table}.espacio_id
                  AND m.usuario_id = nullif(current_setting('app.user_id', true), '')::uuid
                  AND m.rol IN ('owner','editor')
            )
        """
        op.execute(f"""ALTER POLICY {table}_anular_importados ON public.{table}
            USING ({editor} AND anulado_en IS NULL) WITH CHECK ({editor} AND anulado_en IS NOT NULL)""")


def upgrade():
    set_policies(imported_only=False)


def downgrade():
    set_policies(imported_only=True)
