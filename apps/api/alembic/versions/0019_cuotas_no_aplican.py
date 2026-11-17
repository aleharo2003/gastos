"""Conservar cuotas que no corresponden al periodo."""
from alembic import op
import sqlalchemy as sa

revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None

GENERATOR = """CREATE OR REPLACE FUNCTION public.generar_cuotas_mes() RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog
    AS $function$
    DECLARE
        hoy date := (CURRENT_TIMESTAMP AT TIME ZONE 'America/Argentina/Buenos_Aires')::date;
        inicio date;
        ultimo date;
        c public.compromisos%ROWTYPE;
        creadas integer := 0;
        n integer;
    BEGIN
        inicio := hoy - (EXTRACT(day FROM hoy)::integer - 1);
        ultimo := (inicio + interval '1 month - 1 day')::date;
        -- Bloqueo global: un reintento concurrente no recorre todos los planes otra vez.
        PERFORM pg_advisory_xact_lock(17617,1);
        FOR c IN SELECT * FROM public.compromisos
            WHERE total_cuotas IS NULL AND NOT pausado AND primer_vencimiento<=ultimo
            ORDER BY id FOR UPDATE
        LOOP
            INSERT INTO public.cuotas(id,espacio_id,compromiso_id,numero,vencimiento,importe,estimado)
            VALUES (pg_catalog.gen_random_uuid(),c.espacio_id,c.id,
                (EXTRACT(year FROM inicio)::integer-EXTRACT(year FROM c.primer_vencimiento)::integer)*12
                    + EXTRACT(month FROM inicio)::integer-EXTRACT(month FROM c.primer_vencimiento)::integer+1,
                inicio + (LEAST(EXTRACT(day FROM c.primer_vencimiento)::integer,
                    EXTRACT(day FROM ultimo)::integer)-1),
                CASE WHEN c.variable THEN COALESCE((SELECT q.importe FROM public.cuotas q
                    WHERE q.espacio_id=c.espacio_id AND q.compromiso_id=c.id AND q.periodo<inicio
                    ORDER BY q.periodo DESC LIMIT 1),c.importe) ELSE c.importe END,c.variable)
            ON CONFLICT (espacio_id,compromiso_id,periodo) DO NOTHING;
            GET DIAGNOSTICS n = ROW_COUNT;
            creadas := creadas+n;
        END LOOP;
        RETURN creadas;
    END
    $function$"""


def upgrade():
    op.add_column('cuotas', sa.Column('no_aplica', sa.Boolean(), nullable=False,
        server_default=sa.false()), schema='public')
    op.execute("""CREATE POLICY cuotas_alta_aplicable ON public.cuotas
        AS RESTRICTIVE FOR INSERT TO app_runtime WITH CHECK (NOT no_aplica)""")
    op.execute("""ALTER POLICY cuotas_confirmacion ON public.cuotas
        USING (NOT no_aplica AND NOT EXISTS (SELECT 1 FROM public.pagos_cuota p
            WHERE p.espacio_id=cuotas.espacio_id AND p.cuota_id=cuotas.id))
        WITH CHECK (NOT estimado)""")
    op.execute("""CREATE FUNCTION public.validar_cambio_cuota() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
        BEGIN
            IF current_user='app_runtime' AND (
                NEW.version<>OLD.version+1 OR
                (NEW.no_aplica AND NEW.importe<>OLD.importe) OR
                (NOT NEW.no_aplica AND NOT OLD.estimado)
            ) THEN
                RETURN NULL;
            END IF;
            RETURN NEW;
        END
        $fn$""")
    op.execute("""REVOKE ALL ON FUNCTION public.validar_cambio_cuota()
        FROM PUBLIC, anon, authenticated, service_role, app_runtime""")
    op.execute("""CREATE TRIGGER validar_cambio_cuota BEFORE UPDATE ON public.cuotas
        FOR EACH ROW EXECUTE FUNCTION public.validar_cambio_cuota()""")
    op.execute('GRANT UPDATE(no_aplica) ON public.cuotas TO app_runtime')
    op.execute("""CREATE POLICY pagos_cuota_aplicable ON public.pagos_cuota
        AS RESTRICTIVE FOR INSERT TO app_runtime WITH CHECK (
            EXISTS (SELECT 1 FROM public.cuotas q WHERE q.id=pagos_cuota.cuota_id
                AND q.espacio_id=pagos_cuota.espacio_id AND NOT q.no_aplica AND NOT q.estimado))""")
    op.execute(GENERATOR.replace('q.periodo<inicio', 'q.periodo<inicio AND NOT q.no_aplica'))


def downgrade():
    op.execute("""DO $check$ BEGIN
        IF EXISTS (SELECT 1 FROM public.cuotas WHERE no_aplica)
        THEN RAISE EXCEPTION 'Hay cuotas no aplicables; resolver sus estados antes del downgrade.';
        END IF;
        END $check$""")
    op.execute(GENERATOR)
    op.execute('DROP POLICY pagos_cuota_aplicable ON public.pagos_cuota')
    op.execute('DROP TRIGGER validar_cambio_cuota ON public.cuotas')
    op.execute('DROP FUNCTION public.validar_cambio_cuota()')
    op.execute('DROP POLICY cuotas_alta_aplicable ON public.cuotas')
    op.execute("""ALTER POLICY cuotas_confirmacion ON public.cuotas
        USING (estimado AND NOT EXISTS (SELECT 1 FROM public.pagos_cuota p
            WHERE p.espacio_id=cuotas.espacio_id AND p.cuota_id=cuotas.id))
        WITH CHECK (NOT estimado)""")
    op.drop_column('cuotas', 'no_aplica', schema='public')
