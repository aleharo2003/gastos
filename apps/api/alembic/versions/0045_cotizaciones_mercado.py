"""Cotizaciones de mercado y tipo preferido por espacio."""
from alembic import op
import sqlalchemy as sa

revision = '0045'
down_revision = '0044'
branch_labels = None
depends_on = None

TYPES = "'oficial', 'blue', 'bolsa', 'contadoconliqui', 'mayorista', 'cripto', 'tarjeta'"


def upgrade():
    op.create_table('cotizaciones_mercado',
        sa.Column('tipo', sa.Text(), primary_key=True),
        sa.Column('fecha', sa.Date(), primary_key=True),
        sa.Column('tasa', sa.Numeric(12, 4), nullable=False),
        sa.Column('actualizada_en', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f'tipo IN ({TYPES}) AND tasa > 0 AND tasa < 100000000', name='ck_cotizaciones_mercado'),
        schema='public')
    op.create_table('preferencias_cotizacion',
        sa.Column('espacio_id', sa.Uuid(), sa.ForeignKey('public.espacios.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('tipo', sa.Text(), nullable=False),
        sa.CheckConstraint(f'tipo IN ({TYPES})', name='ck_preferencias_cotizacion'),
        schema='public')
    for name in ('cotizaciones_mercado', 'preferencias_cotizacion'):
        table = 'public.' + name
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY cotizacion_migrator ON {table} TO app_migrator USING (true) WITH CHECK (true)')
        op.execute(f'REVOKE ALL ON {table} FROM PUBLIC, anon, authenticated, service_role, app_runtime')
        op.execute(f'GRANT SELECT ON {table} TO app_runtime')
    op.execute('CREATE POLICY cotizacion_read ON public.cotizaciones_mercado FOR SELECT TO app_runtime USING (true)')
    pref = 'public.preferencias_cotizacion'
    scope = """espacio_id=NULLIF(current_setting('app.workspace_id', true),'')::uuid
       AND EXISTS (SELECT FROM public.miembros_espacio m
         WHERE m.espacio_id=preferencias_cotizacion.espacio_id
         AND m.usuario_id=NULLIF(current_setting('app.user_id', true),'')::uuid {role})"""
    reader = scope.format(role='')
    writer = scope.format(role="AND m.rol IN ('owner','editor')")
    op.execute(f'CREATE POLICY cotizacion_read ON {pref} FOR SELECT TO app_runtime USING ({reader})')
    op.execute(f'CREATE POLICY cotizacion_insert ON {pref} FOR INSERT TO app_runtime WITH CHECK ({writer})')
    op.execute(f'CREATE POLICY cotizacion_update ON {pref} FOR UPDATE TO app_runtime USING ({writer}) WITH CHECK ({writer})')
    op.execute(f'GRANT INSERT ON {pref} TO app_runtime')
    op.execute(f'GRANT UPDATE (tipo) ON {pref} TO app_runtime')
    op.execute("""
        CREATE FUNCTION public.guardar_cotizaciones_mercado(jsonb) RETURNS void
        LANGUAGE SQL SECURITY DEFINER SET search_path=pg_catalog AS $fn$
        INSERT INTO public.cotizaciones_mercado(tipo, fecha, tasa, actualizada_en)
        SELECT r.tipo, (r.actualizada_en AT TIME ZONE 'America/Argentina/Buenos_Aires')::date,
            r.tasa, r.actualizada_en
        FROM jsonb_to_recordset($1) AS r(tipo text, tasa numeric, actualizada_en timestamptz)
        WHERE r.actualizada_en <= now()
        ON CONFLICT (tipo, fecha) DO UPDATE SET tasa=excluded.tasa, actualizada_en=excluded.actualizada_en
        WHERE cotizaciones_mercado.actualizada_en <= excluded.actualizada_en
        $fn$;
        REVOKE ALL ON FUNCTION public.guardar_cotizaciones_mercado(jsonb)
            FROM PUBLIC, anon, authenticated, service_role, app_runtime;
        DO $grant$ BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname='app_jobs'
                       AND has_function_privilege(oid, 'public.generar_cuotas_mes()', 'EXECUTE')) THEN
                GRANT EXECUTE ON FUNCTION public.guardar_cotizaciones_mercado(jsonb) TO app_jobs;
            END IF;
            IF EXISTS (SELECT FROM pg_roles WHERE rolname='app_backup'
                       AND has_table_privilege(oid, 'public.espacios', 'SELECT')) THEN
                CREATE POLICY respaldo_lectura ON public.preferencias_cotizacion FOR SELECT TO app_backup
                    USING (EXISTS (SELECT FROM public.espacios e WHERE e.id=preferencias_cotizacion.espacio_id));
                GRANT SELECT ON public.preferencias_cotizacion TO app_backup;
            END IF;
        END $grant$;
    """)


def downgrade():
    op.execute('DROP FUNCTION public.guardar_cotizaciones_mercado(jsonb)')
    op.drop_table('preferencias_cotizacion', schema='public')
    op.drop_table('cotizaciones_mercado', schema='public')
