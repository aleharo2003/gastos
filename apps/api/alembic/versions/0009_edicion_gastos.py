"""Edicion de gastos por miembros con permiso de escritura."""
from alembic import op

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade():
    allowed = """espacio_id = nullif(current_setting('app.workspace_id', true), '')::uuid
        AND EXISTS (SELECT 1 FROM public.miembros_espacio m
            WHERE m.espacio_id = gastos.espacio_id
            AND m.usuario_id = nullif(current_setting('app.user_id', true), '')::uuid
            AND m.rol IN ('owner','editor'))"""
    op.execute(f'CREATE POLICY gastos_edicion ON public.gastos FOR UPDATE TO app_runtime USING ({allowed}) WITH CHECK ({allowed})')
    op.execute('GRANT UPDATE (fecha, descripcion, moneda, importe) ON public.gastos TO app_runtime')


def downgrade():
    op.execute('REVOKE UPDATE (fecha, descripcion, moneda, importe) ON public.gastos FROM app_runtime')
    op.execute('DROP POLICY gastos_edicion ON public.gastos')
