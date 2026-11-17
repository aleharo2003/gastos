"""Compromisos variables y confirmacion atomica de estimados."""
from alembic import op
import sqlalchemy as sa
revision='0018'
down_revision='0017'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('compromisos',sa.Column('variable',sa.Boolean(),nullable=False,server_default=sa.false()),schema='public')
    op.create_check_constraint('ck_compromisos_variable','compromisos','NOT variable OR total_cuotas IS NULL',schema='public')
    op.add_column('cuotas',sa.Column('estimado',sa.Boolean(),nullable=False,server_default=sa.false()),schema='public')
    op.add_column('cuotas',sa.Column('version',sa.Integer(),nullable=False,server_default='1'),schema='public')
    op.create_check_constraint('ck_cuotas_version','cuotas','version >= 1',schema='public')
    member="""espacio_id=NULLIF(current_setting('app.workspace_id',true),'')::uuid
        AND EXISTS (SELECT 1 FROM public.miembros_espacio m WHERE m.espacio_id=cuotas.espacio_id
        AND m.usuario_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND m.rol IN ('owner','editor'))"""
    op.execute(f'CREATE POLICY cuotas_update ON public.cuotas FOR UPDATE TO app_runtime USING ({member}) WITH CHECK ({member})')
    op.execute("""CREATE POLICY cuotas_confirmacion ON public.cuotas AS RESTRICTIVE FOR UPDATE TO app_runtime
        USING (estimado AND NOT EXISTS (SELECT 1 FROM public.pagos_cuota p
            WHERE p.espacio_id=cuotas.espacio_id AND p.cuota_id=cuotas.id))
        WITH CHECK (NOT estimado)""")
    op.execute('GRANT UPDATE(importe,estimado,version) ON public.cuotas TO app_runtime')
    op.execute("""CREATE OR REPLACE FUNCTION public.generar_cuotas_mes() RETURNS integer
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
    $function$""")


def downgrade():
    op.execute("""DO $check$ BEGIN
        IF EXISTS (SELECT 1 FROM public.compromisos WHERE variable)
        THEN RAISE EXCEPTION 'Hay gastos variables; convertir su historial explicitamente antes del downgrade.';
        END IF;
    END $check$""")
    op.execute("""CREATE OR REPLACE FUNCTION public.generar_cuotas_mes() RETURNS integer
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
            INSERT INTO public.cuotas(id,espacio_id,compromiso_id,numero,vencimiento,importe)
            VALUES (pg_catalog.gen_random_uuid(),c.espacio_id,c.id,
                (EXTRACT(year FROM inicio)::integer-EXTRACT(year FROM c.primer_vencimiento)::integer)*12
                    + EXTRACT(month FROM inicio)::integer-EXTRACT(month FROM c.primer_vencimiento)::integer+1,
                inicio + (LEAST(EXTRACT(day FROM c.primer_vencimiento)::integer,
                    EXTRACT(day FROM ultimo)::integer)-1),c.importe)
            ON CONFLICT (espacio_id,compromiso_id,periodo) DO NOTHING;
            GET DIAGNOSTICS n = ROW_COUNT;
            creadas := creadas+n;
        END LOOP;
        RETURN creadas;
    END
    $function$""")
    op.execute('DROP POLICY cuotas_confirmacion ON public.cuotas')
    op.execute('DROP POLICY cuotas_update ON public.cuotas')
    op.execute('REVOKE UPDATE(importe,estimado,version) ON public.cuotas FROM app_runtime')
    op.drop_constraint('ck_cuotas_version','cuotas',type_='check',schema='public')
    op.drop_column('cuotas','version',schema='public')
    op.drop_column('cuotas','estimado',schema='public')
    op.drop_constraint('ck_compromisos_variable','compromisos',type_='check',schema='public')
    op.drop_column('compromisos','variable',schema='public')
