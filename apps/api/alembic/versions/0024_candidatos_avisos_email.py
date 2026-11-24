"""Consulta interna de cuotas elegibles para recordatorios por correo."""
from alembic import op

revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE FUNCTION public.candidatos_avisos_email(instante timestamptz)
        RETURNS TABLE (
            usuario_id uuid,
            espacio_id uuid,
            cuota_id uuid,
            fecha_aviso date,
            evento text,
            vencimiento date,
            nombre text,
            numero integer,
            moneda text,
            pendiente numeric,
            estimado boolean,
            pendiente_ajuste boolean
        )
        LANGUAGE sql STABLE STRICT SET search_path = pg_catalog
        AS $fn$
            WITH reloj AS (
                SELECT instante AT TIME ZONE 'America/Argentina/Buenos_Aires' AS ahora
            )
            SELECT pref.usuario_id, pref.espacio_id, q.id, reloj.ahora::date,
                   CASE WHEN q.vencimiento < reloj.ahora::date THEN 'vencida' ELSE 'vencimiento' END,
                   q.vencimiento, c.nombre, q.numero, c.moneda, q.importe - pago.total,
                   q.estimado, q.pendiente_ajuste
            FROM public.preferencias_avisos pref
            CROSS JOIN reloj
            JOIN public.cuotas q ON q.espacio_id = pref.espacio_id AND NOT q.no_aplica
                AND (
                    (pref.vencimientos AND q.vencimiento >= reloj.ahora::date
                     AND q.vencimiento <= reloj.ahora::date + pref.dias_anticipacion)
                    OR (pref.vencidas AND q.vencimiento < reloj.ahora::date)
                )
            JOIN public.compromisos c ON c.id = q.compromiso_id AND c.espacio_id = q.espacio_id
            CROSS JOIN LATERAL (
                SELECT COALESCE(SUM(g.importe), 0) AS total
                FROM public.pagos_cuota p
                JOIN public.gastos g ON g.espacio_id = p.espacio_id AND g.id = p.id
                WHERE p.espacio_id = q.espacio_id AND p.cuota_id = q.id
            ) pago
            WHERE pref.canal = 'email' AND pref.hora_local <= reloj.ahora::time
              AND q.importe > pago.total
        $fn$
    """)
    # El proceso de entrega tendrá su propio punto de entrada, con permisos específicos.
    op.execute("""
        REVOKE ALL ON FUNCTION public.candidatos_avisos_email(timestamptz)
        FROM PUBLIC, anon, authenticated, service_role, app_runtime
    """)


def downgrade():
    op.execute('DROP FUNCTION public.candidatos_avisos_email(timestamptz)')
