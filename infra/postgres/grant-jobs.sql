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
END
$guard$;
GRANT EXECUTE ON FUNCTION public.generar_cuotas_mes() TO app_jobs;
