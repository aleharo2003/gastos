"""Gastos fijos indefinidos y generacion mensual restringida."""
from alembic import op
import sqlalchemy as sa
revision='0017'
down_revision='0016'
branch_labels=None
depends_on=None


def upgrade():
    op.alter_column('compromisos','total_cuotas',nullable=True,schema='public')
    op.add_column('compromisos',sa.Column('pausado',sa.Boolean(),server_default=sa.false(),nullable=False),schema='public')
    op.add_column('compromisos',sa.Column('version',sa.Integer(),server_default='1',nullable=False),schema='public')
    op.create_check_constraint('ck_compromisos_version','compromisos','version >= 1',schema='public')
    op.drop_constraint('ck_cuotas_numero','cuotas',type_='check',schema='public')
    op.create_check_constraint('ck_cuotas_numero','cuotas','numero BETWEEN 1 AND 119988',schema='public')
    op.add_column('cuotas',sa.Column('periodo',sa.Date(),sa.Computed(
        "vencimiento - (EXTRACT(day FROM vencimiento)::integer - 1)",persisted=True),nullable=False),schema='public')
    op.create_unique_constraint('uq_cuotas_compromiso_periodo','cuotas',['espacio_id','compromiso_id','periodo'],schema='public')
    write="""espacio_id=NULLIF(current_setting('app.workspace_id',true),'')::uuid
        AND EXISTS (SELECT 1 FROM public.miembros_espacio m WHERE m.espacio_id=compromisos.espacio_id
        AND m.usuario_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND m.rol IN ('owner','editor'))"""
    op.execute(f'CREATE POLICY compromisos_update ON public.compromisos FOR UPDATE TO app_runtime USING ({write}) WITH CHECK ({write})')
    op.execute('GRANT UPDATE(pausado,version) ON public.compromisos TO app_runtime')
    # No parametros: el llamador no puede escoger espacios, fechas ni montos.
    # El propietario es app_migrator y su policy explicita sigue aplicando con FORCE RLS.
    op.execute("""CREATE FUNCTION public.generar_cuotas_mes() RETURNS integer
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
    op.execute('REVOKE ALL ON FUNCTION public.generar_cuotas_mes() FROM PUBLIC,anon,authenticated,service_role,app_runtime')
    # El GRANT al rol dedicado se realiza con el script administrativo posterior.
    # No se crea un rol ni se entrega CREATEROLE al migrador.


def downgrade():
    op.execute("""DO $check$ BEGIN
        IF EXISTS (SELECT 1 FROM public.compromisos WHERE total_cuotas IS NULL)
        THEN RAISE EXCEPTION 'Hay gastos indefinidos; el downgrade requiere una conversion explicita del historial.';
        END IF;
    END $check$""")
    op.execute('DROP FUNCTION public.generar_cuotas_mes()')
    op.execute('DROP POLICY compromisos_update ON public.compromisos')
    op.execute('REVOKE UPDATE(pausado,version) ON public.compromisos FROM app_runtime')
    op.drop_constraint('uq_cuotas_compromiso_periodo','cuotas',type_='unique',schema='public')
    op.drop_column('cuotas','periodo',schema='public')
    op.drop_constraint('ck_cuotas_numero','cuotas',type_='check',schema='public')
    op.create_check_constraint('ck_cuotas_numero','cuotas','numero BETWEEN 1 AND 600',schema='public')
    op.drop_constraint('ck_compromisos_version','compromisos',type_='check',schema='public')
    op.drop_column('compromisos','version',schema='public')
    op.drop_column('compromisos','pausado',schema='public')
    op.alter_column('compromisos','total_cuotas',nullable=False,schema='public')
