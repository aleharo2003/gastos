-- Ejecutar como app_migrator, después de provision-backup.sql.
-- Pasar el UUID del espacio con psql -v backup_space_id=... -X --file.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL search_path=pg_catalog;
SELECT set_config('piggo.backup_space', :'backup_space_id', true);
DO $grant$
DECLARE
    target uuid := current_setting('piggo.backup_space')::uuid;
    relation text;
    related text[] := ARRAY[
        'miembros_espacio', 'cuentas', 'ingresos', 'gastos', 'transferencias',
        'compromisos', 'cuotas', 'pagos_cuota', 'variaciones_indice', 'metas_ahorro',
        'planes_gasto', 'comprobantes', 'categorias_movimientos', 'preferencias_avisos', 'gastos_pendientes'
    ];
BEGIN
    IF to_regclass('public.gastos_pendientes') IS NULL THEN
        related := array_remove(related, 'gastos_pendientes');
    END IF;
    IF current_user <> 'app_migrator' OR session_user <> 'app_migrator' OR
       NOT EXISTS (SELECT FROM pg_roles r WHERE r.rolname='app_backup' AND r.rolcanlogin
           AND NOT (r.rolsuper OR r.rolbypassrls OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication OR r.rolinherit)
           AND NOT EXISTS (SELECT FROM pg_auth_members WHERE member=r.oid)) THEN
        RAISE EXCEPTION 'Preparar el rol de resguardo y usar app_migrator para conceder permisos.';
    END IF;
    IF NOT EXISTS (SELECT FROM public.miembros_espacio WHERE espacio_id=target AND rol='owner') THEN
        RAISE EXCEPTION 'El espacio configurado debe tener titular.';
    END IF;
    IF EXISTS (
        SELECT FROM pg_class c WHERE c.relnamespace='public'::regnamespace AND c.relkind IN ('r','p','v','m','f')
            AND (has_table_privilege('app_backup',c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                OR has_any_column_privilege('app_backup',c.oid,'INSERT,UPDATE,REFERENCES')
                OR (c.relname <> ALL(related || ARRAY['espacios','perfiles','alembic_version'])
                    AND (has_table_privilege('app_backup',c.oid,'SELECT') OR has_any_column_privilege('app_backup',c.oid,'SELECT'))))
    )
        OR EXISTS (SELECT FROM pg_proc WHERE proowner='app_migrator'::regrole AND has_function_privilege('app_backup',oid,'EXECUTE'))
        OR EXISTS (SELECT FROM pg_class c WHERE c.relnamespace='public'::regnamespace
                   AND c.relname=ANY(related || ARRAY['espacios','perfiles']) AND NOT (c.relrowsecurity AND c.relforcerowsecurity))
    THEN RAISE EXCEPTION 'El rol tiene permisos adicionales o faltan protecciones RLS.'; END IF;
    FOREACH relation IN ARRAY related LOOP
        EXECUTE format('DROP POLICY IF EXISTS respaldo_lectura ON public.%I', relation);
        EXECUTE format('CREATE POLICY respaldo_lectura ON public.%I FOR SELECT TO app_backup USING (espacio_id=%L::uuid)',
                       relation, target);
        EXECUTE format('GRANT SELECT ON public.%I TO app_backup', relation);
    END LOOP;
    DROP POLICY IF EXISTS respaldo_lectura ON public.espacios;
    EXECUTE format('CREATE POLICY respaldo_lectura ON public.espacios FOR SELECT TO app_backup USING (id=%L::uuid)', target);
    GRANT SELECT ON public.espacios TO app_backup;
    DROP POLICY IF EXISTS respaldo_lectura ON public.perfiles;
    CREATE POLICY respaldo_lectura ON public.perfiles FOR SELECT TO app_backup USING (usuario_id IN (
        SELECT usuario_id FROM public.miembros_espacio UNION
        SELECT usuario_id FROM public.ingresos UNION SELECT usuario_id FROM public.gastos UNION
        SELECT usuario_id FROM public.transferencias UNION SELECT usuario_id FROM public.compromisos UNION
        SELECT usuario_id FROM public.metas_ahorro UNION SELECT usuario_id FROM public.preferencias_avisos
    ));
    GRANT SELECT ON public.perfiles TO app_backup;
    GRANT SELECT (version_num) ON public.alembic_version TO app_backup;
END
$grant$;
COMMIT;
