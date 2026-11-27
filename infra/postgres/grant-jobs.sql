-- Ejecutar como app_migrator, despues de provision-jobs.sql.
-- El administrador de roles no necesita heredar propiedad del esquema.
DO $guard$
BEGIN
    IF current_user<>'app_migrator' OR session_user<>'app_migrator' THEN
        RAISE EXCEPTION 'El permiso del generador lo concede app_migrator.';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles r WHERE r.rolname='app_jobs' AND r.rolcanlogin
        AND NOT r.rolsuper AND NOT r.rolbypassrls AND NOT r.rolcreatedb
        AND NOT r.rolcreaterole AND NOT r.rolreplication AND NOT r.rolinherit
        AND NOT EXISTS (SELECT FROM pg_auth_members WHERE member=r.oid)) THEN
        RAISE EXCEPTION 'Preparar primero el rol restringido app_jobs.';
    END IF;
    GRANT EXECUTE ON FUNCTION public.generar_cuotas_mes() TO app_jobs;
    IF to_regprocedure('public.reservar_aviso_push()') IS NOT NULL THEN
        GRANT EXECUTE ON FUNCTION public.reservar_aviso_push() TO app_jobs;
        GRANT EXECUTE ON FUNCTION public.resolver_aviso_push(uuid,text,text,text,text) TO app_jobs;
    END IF;
    IF to_regprocedure('public.marcar_cuotas_vencidas()') IS NOT NULL THEN
        GRANT EXECUTE ON FUNCTION public.marcar_cuotas_vencidas() TO app_jobs;
    END IF;
    IF to_regprocedure('public.guardar_cotizaciones_mercado(jsonb)') IS NOT NULL THEN
        GRANT EXECUTE ON FUNCTION public.guardar_cotizaciones_mercado(jsonb) TO app_jobs;
    END IF;
END
$guard$;
