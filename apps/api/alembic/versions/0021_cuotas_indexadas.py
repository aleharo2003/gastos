"""Generación y recálculo de cuotas indexadas."""
from alembic import op
import sqlalchemy as sa

revision = '0021'
down_revision = '0020'
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
                    WHERE q.espacio_id=c.espacio_id AND q.compromiso_id=c.id AND q.periodo<inicio AND NOT q.no_aplica
                    ORDER BY q.periodo DESC LIMIT 1),c.importe) ELSE c.importe END,c.variable)
            ON CONFLICT (espacio_id,compromiso_id,periodo) DO NOTHING;
            GET DIAGNOSTICS n = ROW_COUNT;
            creadas := creadas+n;
        END LOOP;
        RETURN creadas;
    END
    $function$"""

INDEXED_GENERATOR = """
        FOR c IN SELECT * FROM public.compromisos
            WHERE indice_ajuste IS NOT NULL AND primer_vencimiento <= ultimo AND NOT pausado
              AND NOT EXISTS (
                  SELECT 1 FROM public.cuotas q
                  WHERE q.espacio_id = compromisos.espacio_id AND q.compromiso_id = compromisos.id
                    AND q.numero = compromisos.total_cuotas
              )
            ORDER BY id
        LOOP
            creadas := creadas + public.sincronizar_cuotas_indexadas(c, inicio);
        END LOOP;
"""

SYNC = """CREATE FUNCTION public.sincronizar_cuotas_indexadas(c public.compromisos, mes date)
    RETURNS integer LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
    DECLARE
        periodo_inicial date := date_trunc('month', c.primer_vencimiento::timestamp)::date;
        periodo_cuota date;
        vencimiento_cuota date;
        base numeric := c.importe;
        calculado numeric;
        tasa numeric;
        base_provisoria boolean := false;
        provisorio boolean;
        q public.cuotas%ROWTYPE;
        creadas integer := 0;
        n integer;
    BEGIN
        FOR n IN 1..c.total_cuotas LOOP
            periodo_cuota := (periodo_inicial + make_interval(months => n - 1))::date;
            EXIT WHEN periodo_cuota > greatest(mes, periodo_inicial);
            SELECT * INTO q FROM public.cuotas
            WHERE espacio_id = c.espacio_id AND compromiso_id = c.id AND periodo = periodo_cuota;
            IF q.no_aplica THEN CONTINUE; END IF;
            IF q.id IS NOT NULL AND NOT q.pendiente_ajuste THEN
                base := q.importe;
                base_provisoria := false;
                CONTINUE;
            END IF;

            SELECT i.variacion, i.periodo <> periodo_cuota INTO tasa, provisorio
            FROM public.variaciones_indice i
            WHERE i.espacio_id = c.espacio_id AND i.indice = c.indice_ajuste AND i.periodo <= periodo_cuota
            ORDER BY i.periodo DESC LIMIT 1;
            provisorio := base_provisoria OR coalesce(provisorio, true);
            calculado := greatest(0.01, round(base * (1 + coalesce(tasa, 0) / 100), 2));
            IF calculado >= 1000000000000 THEN
                calculado := base;
                provisorio := true;
            END IF;

            IF q.id IS NULL THEN
                vencimiento_cuota := periodo_cuota + least(
                    extract(day FROM c.primer_vencimiento)::integer - 1,
                    extract(day FROM periodo_cuota + interval '1 month - 1 day')::integer - 1
                );
                INSERT INTO public.cuotas
                    (id, espacio_id, compromiso_id, numero, vencimiento, importe, pendiente_ajuste)
                VALUES (gen_random_uuid(), c.espacio_id, c.id, n, vencimiento_cuota, calculado, provisorio);
                creadas := creadas + 1;
            ELSE
                UPDATE public.cuotas SET importe = calculado, pendiente_ajuste = provisorio, version = version + 1
                WHERE id = q.id AND espacio_id = c.espacio_id
                  AND (importe, pendiente_ajuste) IS DISTINCT FROM (calculado, provisorio)
                  AND NOT EXISTS (
                      SELECT 1 FROM public.pagos_cuota p WHERE p.espacio_id = c.espacio_id AND p.cuota_id = q.id
                  );
            END IF;
            base := calculado;
            base_provisoria := provisorio;
        END LOOP;
        RETURN creadas;
    END
    $fn$"""

PAYMENT_POLICY = """ALTER POLICY pagos_cuota_aplicable ON public.pagos_cuota WITH CHECK (
    EXISTS (SELECT 1 FROM public.cuotas q WHERE q.id = pagos_cuota.cuota_id
        AND q.espacio_id = pagos_cuota.espacio_id AND NOT q.no_aplica AND NOT q.estimado{condition})
)"""


def upgrade():
    op.add_column('compromisos', sa.Column('indice_ajuste', sa.Text()), schema='public')
    op.create_check_constraint(
        'ck_compromisos_indice', 'compromisos',
        'indice_ajuste IS NULL OR (total_cuotas IS NOT NULL AND NOT variable AND '
        'indice_ajuste = btrim(indice_ajuste) AND char_length(indice_ajuste) BETWEEN 1 AND 80)',
        schema='public',
    )
    op.add_column('cuotas', sa.Column('pendiente_ajuste', sa.Boolean(), nullable=False,
                                     server_default=sa.false()), schema='public')
    op.execute("""ALTER POLICY cuotas_alta_aplicable ON public.cuotas
        WITH CHECK (NOT no_aplica AND NOT pendiente_ajuste)""")
    op.execute("""CREATE POLICY cuotas_provisorias ON public.cuotas AS RESTRICTIVE FOR UPDATE
        TO app_runtime USING (NOT pendiente_ajuste) WITH CHECK (NOT pendiente_ajuste)""")
    op.execute(PAYMENT_POLICY.format(condition=' AND NOT q.pendiente_ajuste'))
    op.execute(SYNC)
    op.execute("""CREATE FUNCTION public.iniciar_cuotas_indexadas() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $fn$
        BEGIN
            PERFORM pg_advisory_xact_lock(17617, 1);
            PERFORM public.sincronizar_cuotas_indexadas(NEW, date_trunc('month',
                CURRENT_TIMESTAMP AT TIME ZONE 'America/Argentina/Buenos_Aires')::date);
            RETURN NULL;
        END
        $fn$""")
    op.execute("""CREATE FUNCTION public.recalcular_cuotas_indexadas() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $fn$
        DECLARE c public.compromisos%ROWTYPE;
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM indices_nuevos) THEN RETURN NULL; END IF;
            PERFORM pg_advisory_xact_lock(17617, 1);
            FOR c IN SELECT * FROM public.compromisos p
                WHERE EXISTS (SELECT 1 FROM indices_nuevos i
                    WHERE i.espacio_id = p.espacio_id AND i.indice = p.indice_ajuste)
                ORDER BY p.id
            LOOP
                PERFORM public.sincronizar_cuotas_indexadas(c, date_trunc('month',
                    CURRENT_TIMESTAMP AT TIME ZONE 'America/Argentina/Buenos_Aires')::date);
            END LOOP;
            RETURN NULL;
        END
        $fn$""")
    for signature in (
        'sincronizar_cuotas_indexadas(public.compromisos,date)',
        'iniciar_cuotas_indexadas()', 'recalcular_cuotas_indexadas()',
    ):
        op.execute(f'REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC, anon, authenticated, service_role, app_runtime')
    op.execute("""CREATE TRIGGER iniciar_cuotas_indexadas AFTER INSERT ON public.compromisos
        FOR EACH ROW WHEN (NEW.indice_ajuste IS NOT NULL) EXECUTE FUNCTION public.iniciar_cuotas_indexadas()""")
    op.execute("""CREATE TRIGGER recalcular_cuotas_indexadas AFTER INSERT ON public.variaciones_indice
        REFERENCING NEW TABLE AS indices_nuevos FOR EACH STATEMENT EXECUTE FUNCTION public.recalcular_cuotas_indexadas()""")
    op.execute(GENERATOR.replace('        RETURN creadas;', INDEXED_GENERATOR + '        RETURN creadas;'))


def downgrade():
    op.execute("""DO $check$ BEGIN
        IF EXISTS (SELECT 1 FROM public.compromisos WHERE indice_ajuste IS NOT NULL)
        THEN RAISE EXCEPTION 'Hay deudas indexadas; resolver sus cuotas antes de revertir la migración.';
        END IF;
        END $check$""")
    op.execute(GENERATOR)
    op.execute('DROP TRIGGER recalcular_cuotas_indexadas ON public.variaciones_indice')
    op.execute('DROP TRIGGER iniciar_cuotas_indexadas ON public.compromisos')
    op.execute('DROP FUNCTION public.recalcular_cuotas_indexadas()')
    op.execute('DROP FUNCTION public.iniciar_cuotas_indexadas()')
    op.execute('DROP FUNCTION public.sincronizar_cuotas_indexadas(public.compromisos,date)')
    op.execute(PAYMENT_POLICY.format(condition=''))
    op.execute('DROP POLICY cuotas_provisorias ON public.cuotas')
    op.execute('ALTER POLICY cuotas_alta_aplicable ON public.cuotas WITH CHECK (NOT no_aplica)')
    op.drop_column('cuotas', 'pendiente_ajuste', schema='public')
    op.drop_constraint('ck_compromisos_indice', 'compromisos', type_='check', schema='public')
    op.drop_column('compromisos', 'indice_ajuste', schema='public')
