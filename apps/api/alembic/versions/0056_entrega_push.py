"""Reserva y resuelve entregas Web Push para el ejecutor de tareas."""
from alembic import op
import sqlalchemy as sa

revision = '0056'
down_revision = '0055'
branch_labels = None
depends_on = None

SIGNATURES = (
    'reservar_aviso_push()',
    'resolver_aviso_push(uuid,text,text,text,text)',
)


def upgrade():
    for name, kind in (
        ('fecha_aviso', sa.Date()), ('ultimo_intento', sa.DateTime(timezone=True)),
        ('intento_id', sa.Uuid()), ('estado_aviso', sa.Text()),
    ):
        op.add_column('suscripciones_push', sa.Column(name, kind), schema='public')
    op.create_unique_constraint('uq_suscripciones_push_intento', 'suscripciones_push',
                                ['intento_id'], schema='public')
    op.create_check_constraint('ck_suscripciones_push_estado', 'suscripciones_push',
                               "estado_aviso IN ('reservado','aceptado','reintento','incierto')", schema='public')
    op.execute("""
        CREATE FUNCTION public.reservar_aviso_push()
        RETURNS TABLE (intento_id uuid, endpoint text, p256dh text, auth text)
        LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $fn$
            WITH reloj AS (
                SELECT statement_timestamp() AS instante,
                       statement_timestamp() AT TIME ZONE 'America/Argentina/Buenos_Aires' AS ahora
            ), candidato AS (
                SELECT s.usuario_id, s.espacio_id, s.dispositivo_id, r.instante, r.ahora::date AS hoy
                FROM public.suscripciones_push s
                JOIN public.preferencias_avisos p USING (usuario_id,espacio_id)
                CROSS JOIN reloj r
                WHERE p.canal='push' AND p.hora_local<=r.ahora::time
                  AND (s.fecha_aviso IS NULL OR s.fecha_aviso<r.ahora::date
                       OR (s.fecha_aviso=r.ahora::date AND s.estado_aviso='reintento'
                           AND s.ultimo_intento <= r.instante - interval '30 minutes'))
                  AND EXISTS (
                      SELECT FROM public.cuotas q
                      WHERE q.espacio_id=p.espacio_id AND NOT q.no_aplica
                        AND ((p.vencimientos AND q.vencimiento BETWEEN r.ahora::date AND r.ahora::date+p.dias_anticipacion)
                             OR (p.vencidas AND q.vencimiento<r.ahora::date))
                        AND q.importe>COALESCE((
                            SELECT SUM(g.importe) FROM public.pagos_cuota t
                            JOIN public.gastos g ON g.espacio_id=t.espacio_id AND g.id=t.id
                            WHERE t.espacio_id=q.espacio_id AND t.cuota_id=q.id
                        ),0)
                  )
                ORDER BY s.fecha_aviso NULLS FIRST, s.ultimo_intento NULLS FIRST, s.dispositivo_id, s.usuario_id, s.espacio_id
                LIMIT 1 FOR UPDATE OF s SKIP LOCKED
            )
            UPDATE public.suscripciones_push s
               SET fecha_aviso=c.hoy, ultimo_intento=c.instante,
                   intento_id=gen_random_uuid(), estado_aviso='reservado'
              FROM candidato c
             WHERE (s.usuario_id,s.espacio_id,s.dispositivo_id)=(c.usuario_id,c.espacio_id,c.dispositivo_id)
            RETURNING s.intento_id,s.endpoint,s.p256dh,s.auth
        $fn$;

        CREATE FUNCTION public.resolver_aviso_push(intento uuid, resultado text, destino text, clave text, secreto text)
        RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $fn$
        BEGIN
            IF resultado='vencido' THEN
                DELETE FROM public.suscripciones_push s WHERE s.intento_id=intento
                    AND s.estado_aviso='reservado' AND (s.endpoint,s.p256dh,s.auth)=(destino,clave,secreto);
            ELSE
                UPDATE public.suscripciones_push s SET estado_aviso=resultado WHERE s.intento_id=intento
                    AND s.estado_aviso='reservado' AND (s.endpoint,s.p256dh,s.auth)=(destino,clave,secreto)
                    AND resultado IN ('aceptado','reintento','incierto');
            END IF;
            RETURN FOUND;
        END
        $fn$;
    """)
    for signature in SIGNATURES:
        op.execute(f'REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC, anon, authenticated, service_role, app_runtime')
        op.execute(f"""DO $grant$ BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname='app_jobs'
                       AND has_function_privilege(oid, 'public.generar_cuotas_mes()', 'EXECUTE')) THEN
                GRANT EXECUTE ON FUNCTION public.{signature} TO app_jobs;
            END IF;
        END $grant$""")


def downgrade():
    for signature in reversed(SIGNATURES):
        op.execute(f'DROP FUNCTION public.{signature}')
    op.drop_constraint('ck_suscripciones_push_estado', 'suscripciones_push', schema='public', type_='check')
    op.drop_constraint('uq_suscripciones_push_intento', 'suscripciones_push', schema='public', type_='unique')
    for name in ('estado_aviso', 'intento_id', 'ultimo_intento', 'fecha_aviso'):
        op.drop_column('suscripciones_push', name, schema='public')
