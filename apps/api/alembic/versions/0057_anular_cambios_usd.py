"""Anula cambios de moneda sin eliminar su historial."""
from alembic import op
import sqlalchemy as sa

revision = '0057'
down_revision = '0056'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('ventas_usd', sa.Column('anulado_en', sa.DateTime(timezone=True)), schema='public')
    editor = """espacio_id=nullif(current_setting('app.workspace_id',true),'')::uuid
        AND EXISTS (
            SELECT FROM public.miembros_espacio m WHERE m.espacio_id=ventas_usd.espacio_id
                AND m.usuario_id=nullif(current_setting('app.user_id',true),'')::uuid
                AND m.rol IN ('owner','editor')
        )"""
    op.execute(f"""CREATE POLICY ventas_anular ON public.ventas_usd FOR UPDATE TO app_runtime
        USING ({editor} AND anulado_en IS NULL) WITH CHECK ({editor} AND anulado_en IS NOT NULL)""")
    op.execute('GRANT UPDATE (anulado_en) ON public.ventas_usd TO app_runtime')


def downgrade():
    op.execute("""DO $ BEGIN
        IF EXISTS (SELECT 1 FROM public.ventas_usd WHERE anulado_en IS NOT NULL) THEN
            RAISE EXCEPTION 'Hay cambios anulados y se debe conservar su historial';
        END IF;
    END $""")
    op.execute('DROP POLICY ventas_anular ON public.ventas_usd')
    op.drop_column('ventas_usd', 'anulado_en', schema='public')
