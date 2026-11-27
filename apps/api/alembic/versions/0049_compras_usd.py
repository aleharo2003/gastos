"""Registra compras de USD con los importes y cuentas de la operación."""
from alembic import op
import sqlalchemy as sa

revision = '0049'
down_revision = '0048'
branch_labels = None
depends_on = None


def set_insert_policy(source, destination):
    op.execute(f"""ALTER POLICY ventas_insert ON public.ventas_usd WITH CHECK (
        espacio_id=NULLIF(current_setting('app.workspace_id',true),'')::uuid
        AND EXISTS (SELECT FROM public.miembros_espacio m WHERE m.espacio_id=ventas_usd.espacio_id
            AND m.usuario_id=NULLIF(current_setting('app.user_id',true),'')::uuid
            AND m.rol IN ('owner','editor'))
        AND EXISTS (SELECT FROM public.cuentas c WHERE c.espacio_id=ventas_usd.espacio_id
          AND c.id=ventas_usd.origen_id AND c.activa AND (c.moneda IS NULL OR c.moneda={source}))
        AND EXISTS (SELECT FROM public.cuentas c WHERE c.espacio_id=ventas_usd.espacio_id
          AND c.id=ventas_usd.destino_id AND c.activa AND (c.moneda IS NULL OR c.moneda={destination})))""")


def upgrade():
    op.add_column('ventas_usd', sa.Column('tipo', sa.Text(), nullable=False, server_default='venta'), schema='public')
    op.create_check_constraint('ck_ventas_usd_tipo', 'ventas_usd', "tipo IN ('venta','compra')", schema='public')
    set_insert_policy(
        "CASE WHEN ventas_usd.tipo='compra' THEN 'ARS' ELSE 'USD' END",
        "CASE WHEN ventas_usd.tipo='compra' THEN 'USD' ELSE 'ARS' END",
    )


def downgrade():
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM public.ventas_usd WHERE tipo='compra') THEN
            RAISE EXCEPTION 'Hay compras registradas y se requiere conservar su tipo';
        END IF;
    END $$""")
    set_insert_policy("'USD'", "'ARS'")
    op.drop_constraint('ck_ventas_usd_tipo', 'ventas_usd', schema='public', type_='check')
    op.drop_column('ventas_usd', 'tipo', schema='public')
