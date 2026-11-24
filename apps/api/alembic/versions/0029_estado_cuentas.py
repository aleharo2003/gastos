"""Desactivación de cuentas con conservación de movimientos."""
from alembic import op
import sqlalchemy as sa

revision = '0029'
down_revision = '0028'
branch_labels = None
depends_on = None

TABLES = ('gastos', 'ingresos', 'transferencias', 'compromisos', 'metas_ahorro')


def upgrade() -> None:
    op.add_column('cuentas', sa.Column('activa', sa.Boolean(), nullable=False,
                                      server_default=sa.true()), schema='public')
    op.execute('GRANT UPDATE (activa) ON TABLE public.cuentas TO app_runtime')
    op.execute("""
    CREATE FUNCTION public.verificar_cuentas_activas() RETURNS trigger
    LANGUAGE plpgsql SET search_path TO pg_catalog, public
    AS $$
    DECLARE
        ids uuid[];
        estado boolean;
    BEGIN
        IF TG_TABLE_NAME = 'transferencias' THEN
            ids := ARRAY[NEW.origen_id, NEW.destino_id];
        ELSE
            ids := ARRAY[NEW.cuenta_id];
        END IF;
        FOR estado IN
            SELECT activa FROM public.cuentas
            WHERE espacio_id = NEW.espacio_id AND id = ANY(ids)
            ORDER BY id FOR SHARE
        LOOP
            IF NOT estado THEN
                RAISE EXCEPTION 'Cuenta inactiva' USING
                    ERRCODE = '23514', CONSTRAINT = 'cuenta_activa_para_movimientos';
            END IF;
        END LOOP;
        RETURN NULL;
    END
    $$;
    """)
    for table in TABLES:
        op.execute(f"""
            CREATE TRIGGER verificar_cuentas_activas
            AFTER INSERT ON public.{table} FOR EACH ROW
            EXECUTE FUNCTION public.verificar_cuentas_activas()
        """)


def downgrade() -> None:
    for table in TABLES:
        op.execute(f'DROP TRIGGER verificar_cuentas_activas ON public.{table}')
    op.execute('DROP FUNCTION public.verificar_cuentas_activas()')
    op.drop_column('cuentas', 'activa', schema='public')
