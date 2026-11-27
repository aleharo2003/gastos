"""Registra el primer marcado diario de una cuota vencida."""
from alembic import op
import sqlalchemy as sa

revision = '0051'
down_revision = '0050'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('cuotas', sa.Column('marcada_vencida_el', sa.Date()), schema='public')
    op.create_check_constraint(
        'ck_cuotas_marcada_vencida', 'cuotas', 'marcada_vencida_el > vencimiento', schema='public',
    )
    op.execute("""
        CREATE FUNCTION public.marcar_cuotas_vencidas() RETURNS integer
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog
        AS $fn$
        DECLARE
            hoy date := (CURRENT_TIMESTAMP AT TIME ZONE 'America/Argentina/Buenos_Aires')::date;
            cuota record;
            marcadas integer := 0;
            afectadas integer;
        BEGIN
            PERFORM pg_advisory_xact_lock(17617, 2);
            FOR cuota IN
                SELECT q.id, q.espacio_id FROM public.cuotas q
                WHERE q.marcada_vencida_el IS NULL AND NOT q.no_aplica AND NOT q.estimado
                  AND q.vencimiento < hoy
                  AND q.importe > COALESCE((
                      SELECT SUM(g.importe) FROM public.pagos_cuota p
                      JOIN public.gastos g ON g.espacio_id=p.espacio_id AND g.id=p.id
                      WHERE p.espacio_id=q.espacio_id AND p.cuota_id=q.id
                  ), 0)
                ORDER BY q.id
            LOOP
                -- Releer el saldo con el mismo bloqueo que usa el pago de una cuota.
                PERFORM pg_advisory_xact_lock(hashtextextended(
                    format('cuota:%s:%s', cuota.espacio_id, cuota.id), 0));
                UPDATE public.cuotas q SET marcada_vencida_el=hoy
                WHERE q.espacio_id=cuota.espacio_id AND q.id=cuota.id
                  AND q.marcada_vencida_el IS NULL AND NOT q.no_aplica AND NOT q.estimado
                  AND q.vencimiento < hoy
                  AND q.importe > COALESCE((
                      SELECT SUM(g.importe) FROM public.pagos_cuota p
                      JOIN public.gastos g ON g.espacio_id=p.espacio_id AND g.id=p.id
                      WHERE p.espacio_id=q.espacio_id AND p.cuota_id=q.id
                  ), 0);
                GET DIAGNOSTICS afectadas = ROW_COUNT;
                marcadas := marcadas + afectadas;
            END LOOP;
            RETURN marcadas;
        END
        $fn$;
        REVOKE ALL ON FUNCTION public.marcar_cuotas_vencidas()
            FROM PUBLIC, anon, authenticated, service_role, app_runtime;
        DO $grant$ BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname='app_jobs'
                       AND has_function_privilege(oid, 'public.generar_cuotas_mes()', 'EXECUTE')) THEN
                GRANT EXECUTE ON FUNCTION public.marcar_cuotas_vencidas() TO app_jobs;
            END IF;
        END $grant$;
    """)


def downgrade():
    op.execute('DROP FUNCTION public.marcar_cuotas_vencidas()')
    op.drop_constraint('ck_cuotas_marcada_vencida', 'cuotas', schema='public', type_='check')
    op.drop_column('cuotas', 'marcada_vencida_el', schema='public')
