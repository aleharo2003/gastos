"""Respetar la moneda de una cuenta en los movimientos nuevos y sus cambios."""
from alembic import op

revision = '0043'
down_revision = '0042'
branch_labels = None
depends_on = None

TABLES = {
    'gastos': ('cuenta_id',),
    'ingresos': ('cuenta_id',),
    'transferencias': ('origen_id', 'destino_id'),
    'gastos_pendientes': ('cuenta_id',),
    'compromisos': ('cuenta_id',),
    'metas_ahorro': ('cuenta_id',),
}


def upgrade():
    op.execute("""
        CREATE FUNCTION public.verificar_moneda_cuentas() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog
        AS $moneda$
        DECLARE
            cuentas uuid[];
            anteriores uuid[];
        BEGIN
            IF TG_TABLE_NAME = 'transferencias' THEN
                cuentas := ARRAY[NEW.origen_id, NEW.destino_id];
                IF TG_OP = 'UPDATE' THEN
                    anteriores := ARRAY[OLD.origen_id, OLD.destino_id];
                END IF;
            ELSE
                cuentas := ARRAY[NEW.cuenta_id];
                IF TG_OP = 'UPDATE' THEN
                    anteriores := ARRAY[OLD.cuenta_id];
                END IF;
            END IF;

            IF TG_OP = 'UPDATE' THEN
                IF OLD.moneda IS NOT DISTINCT FROM NEW.moneda
                    AND anteriores IS NOT DISTINCT FROM cuentas THEN
                    RETURN NULL;
                END IF;
            END IF;

            IF EXISTS (
                SELECT 1 FROM public.cuentas
                WHERE espacio_id = NEW.espacio_id AND id = ANY(cuentas)
                  AND moneda IS NOT NULL AND moneda <> NEW.moneda
            ) THEN
                RAISE EXCEPTION 'La moneda del movimiento debe coincidir con la de la cuenta'
                    USING ERRCODE = '23514', CONSTRAINT = 'moneda_de_cuenta';
            END IF;
            RETURN NULL;
        END;
        $moneda$;
    """)
    op.execute('REVOKE ALL ON FUNCTION public.verificar_moneda_cuentas() '
               'FROM PUBLIC, anon, authenticated, service_role')
    for table, keys in TABLES.items():
        columns = ', '.join(('moneda', *keys))
        op.execute(f"""
            CREATE TRIGGER verificar_moneda_cuentas
            AFTER INSERT OR UPDATE OF {columns} ON public.{table}
            FOR EACH ROW EXECUTE FUNCTION public.verificar_moneda_cuentas()
        """)


def downgrade():
    for table in TABLES:
        op.execute(f'DROP TRIGGER verificar_moneda_cuentas ON public.{table}')
    op.execute('DROP FUNCTION public.verificar_moneda_cuentas()')
