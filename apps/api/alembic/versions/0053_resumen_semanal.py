"""Resumen semanal limitado a la membresía del piloto de correo."""
from alembic import op
import sqlalchemy as sa

revision = '0053'
down_revision = '0052'
branch_labels = None
depends_on = None

SIGNATURES = (
    'resumen_semanal_piloto(uuid,uuid,timestamptz)',
    'reservar_resumen_semanal_piloto(uuid,uuid,timestamptz,uuid)',
    'resolver_resumen_semanal_piloto(uuid,text)',
)


def upgrade():
    op.create_table(
        'envios_resumen_semanal',
        sa.Column('usuario_id', sa.Uuid(), primary_key=True),
        sa.Column('espacio_id', sa.Uuid(), primary_key=True),
        sa.Column('semana', sa.Date(), primary_key=True),
        sa.Column('intento_id', sa.Uuid(), nullable=False),
        sa.Column('estado', sa.Text(), nullable=False),
        sa.CheckConstraint("estado IN ('reservado','aceptada','reintento','incierta')", name='ck_envios_resumen_semanal_estado'),
        sa.UniqueConstraint('intento_id', name='uq_envios_resumen_semanal_intento'),
        sa.ForeignKeyConstraint(['usuario_id', 'espacio_id'],
                                ['public.miembros_espacio.usuario_id', 'public.miembros_espacio.espacio_id'],
                                name='fk_envios_resumen_semanal_miembro', ondelete='CASCADE'),
        schema='public',
    )
    table = 'public.envios_resumen_semanal'
    op.execute(f'REVOKE ALL ON {table} FROM PUBLIC, anon, authenticated, service_role, app_runtime')
    op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY envios_resumen_semanal_migrator ON {table} TO app_migrator USING (true) WITH CHECK (true)')
    op.execute("""
        CREATE FUNCTION public.resumen_semanal_piloto(usuario uuid, espacio uuid, instante timestamptz)
        RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $fn$
        DECLARE
            ahora timestamp := instante AT TIME ZONE 'America/Argentina/Buenos_Aires';
            hoy date := ahora::date;
            lunes date := date_trunc('week', ahora)::date;
        BEGIN
            PERFORM public.comprobar_piloto_avisos_email(usuario, espacio);
            IF NOT EXISTS (
                SELECT FROM public.preferencias_avisos p
                WHERE p.usuario_id=usuario AND p.espacio_id=espacio
                    AND p.canal='email' AND p.resumen_semanal
            ) THEN RETURN NULL; END IF;

            RETURN (
                WITH gastos AS (
                    SELECT g.moneda, SUM(g.importe) AS total,
                           COALESCE(SUM(g.importe) FILTER (WHERE g.tasa_pago IS NOT NULL), 0) AS usd_fijo,
                           COALESCE(SUM(round(g.importe*g.tasa_pago,2)), 0) AS ars_fijo
                    FROM public.gastos g
                    WHERE g.espacio_id=espacio AND g.anulado_en IS NULL AND g.fecha>=lunes-7 AND g.fecha<lunes
                    GROUP BY g.moneda
                ), proximos AS (
                    SELECT q.vencimiento, c.nombre, c.moneda, q.importe-COALESCE(p.pagado,0) AS saldo,
                           q.estimado OR q.pendiente_ajuste AS estimado, q.id
                    FROM public.cuotas q
                    JOIN public.compromisos c ON c.espacio_id=q.espacio_id AND c.id=q.compromiso_id
                    LEFT JOIN LATERAL (
                        SELECT SUM(g.importe) AS pagado FROM public.pagos_cuota pc
                        JOIN public.gastos g ON g.espacio_id=pc.espacio_id AND g.id=pc.id
                        WHERE pc.espacio_id=q.espacio_id AND pc.cuota_id=q.id
                    ) p ON true
                    WHERE q.espacio_id=espacio AND NOT q.no_aplica AND q.importe>COALESCE(p.pagado,0)
                        AND q.vencimiento>=hoy AND q.vencimiento<hoy+7
                    UNION ALL
                    SELECT p.fecha_vencimiento, p.descripcion, p.moneda, p.importe, false, p.id
                    FROM public.gastos_pendientes p
                    WHERE p.espacio_id=espacio AND p.gasto_id IS NULL
                        AND p.fecha_vencimiento>=hoy AND p.fecha_vencimiento<hoy+7
                ), limite AS (
                    SELECT p.datos->'limites'->'semanal' AS datos
                    FROM public.planes_gasto p WHERE p.espacio_id=espacio
                ), tasa AS (
                    SELECT v.tasa FROM (
                        SELECT m.fecha, m.tasa, 1 AS prioridad FROM public.cotizaciones_manuales m
                        WHERE m.espacio_id=espacio AND m.fecha<lunes
                        UNION ALL
                        SELECT m.fecha, m.tasa, 0 FROM public.cotizaciones_mercado m
                        WHERE m.fecha<lunes AND m.tipo=COALESCE((
                            SELECT pr.tipo FROM public.preferencias_cotizacion pr WHERE pr.espacio_id=espacio
                        ), 'oficial')
                    ) v ORDER BY v.fecha DESC, v.prioridad DESC LIMIT 1
                )
                SELECT jsonb_build_object(
                    'desde', lunes-7, 'hasta', lunes-1, 'proximos_desde', hoy,
                    'gastos', COALESCE((SELECT jsonb_agg(jsonb_build_object('moneda', moneda, 'total', total::text)
                                                      ORDER BY moneda) FROM gastos), '[]'::jsonb),
                    'cantidad_proximos', (SELECT count(*) FROM proximos),
                    'proximos', COALESCE((
                        SELECT jsonb_agg(jsonb_build_object('vencimiento', vencimiento, 'nombre', nombre,
                           'moneda', moneda, 'saldo', saldo::text, 'estimado', estimado) ORDER BY vencimiento,id)
                        FROM (SELECT * FROM proximos ORDER BY vencimiento,id LIMIT 10) pagina
                    ), '[]'::jsonb),
                    'limite', (SELECT datos FROM limite),
                    'tasa', (SELECT tasa::text FROM tasa),
                    'gastos_fijados', COALESCE((SELECT jsonb_build_array(usd_fijo::text, ars_fijo::text)
                                              FROM gastos WHERE moneda='USD'), '["0","0"]'::jsonb)
                )
            );
        END
        $fn$;
        CREATE FUNCTION public.reservar_resumen_semanal_piloto(usuario uuid, espacio uuid, instante timestamptz, intento uuid)
        RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $fn$
        DECLARE
            ahora timestamp := instante AT TIME ZONE 'America/Argentina/Buenos_Aires';
        BEGIN
            PERFORM public.comprobar_piloto_avisos_email(usuario, espacio);
            IF NOT EXISTS (
                SELECT FROM public.preferencias_avisos p
                WHERE p.usuario_id=usuario AND p.espacio_id=espacio
                    AND p.canal='email' AND p.resumen_semanal AND p.hora_local<=ahora::time
            ) THEN RETURN false; END IF;

            INSERT INTO public.envios_resumen_semanal AS e(usuario_id,espacio_id,semana,intento_id,estado)
            VALUES (usuario,espacio,date_trunc('week',ahora)::date-7,intento,'reservado')
            ON CONFLICT (usuario_id,espacio_id,semana) DO UPDATE
            SET intento_id=EXCLUDED.intento_id, estado='reservado'
            WHERE e.estado='reintento';
            RETURN FOUND;
        END
        $fn$;
        CREATE FUNCTION public.resolver_resumen_semanal_piloto(intento uuid, resultado text)
        RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $fn$
        BEGIN
            UPDATE public.envios_resumen_semanal e SET estado=resultado
            FROM public.piloto_avisos_email p
            WHERE e.intento_id=intento AND e.usuario_id=p.usuario_id AND e.espacio_id=p.espacio_id
                AND e.estado='reservado' AND resultado IN ('aceptada','reintento','incierta');
            RETURN FOUND;
        END
        $fn$;
    """)
    for signature in SIGNATURES:
        op.execute(f'REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC, anon, authenticated, service_role, app_runtime')
        op.execute(f"""DO $grant$ BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname='app_email_jobs'
                       AND has_function_privilege(oid, 'public.previsualizar_avisos_email_piloto(uuid,uuid,timestamptz)', 'EXECUTE')) THEN
                GRANT EXECUTE ON FUNCTION public.{signature} TO app_email_jobs;
            END IF;
        END $grant$""")


def downgrade():
    for signature in reversed(SIGNATURES):
        op.execute(f'DROP FUNCTION public.{signature}')
    op.drop_table('envios_resumen_semanal', schema='public')
