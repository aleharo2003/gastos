-- Ejecutar como app_migrator, despues de provision-email-pilot.sql.
-- El administrador de roles no necesita heredar propiedad del esquema.
DO $guard$
BEGIN
    IF current_user<>'app_migrator' OR session_user<>'app_migrator' THEN
        RAISE EXCEPTION 'El permiso del piloto lo concede app_migrator.';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles r WHERE r.rolname='app_email_jobs' AND r.rolcanlogin
        AND NOT r.rolsuper AND NOT r.rolbypassrls AND NOT r.rolcreatedb
        AND NOT r.rolcreaterole AND NOT r.rolreplication AND NOT r.rolinherit
        AND NOT EXISTS (SELECT FROM pg_auth_members WHERE member=r.oid)) THEN
        RAISE EXCEPTION 'Preparar primero el rol restringido app_email_jobs.';
    END IF;
    GRANT EXECUTE ON FUNCTION public.previsualizar_avisos_email_piloto(uuid,uuid,timestamptz) TO app_email_jobs;
    GRANT EXECUTE ON FUNCTION public.encolar_avisos_email_piloto(uuid,uuid,timestamptz) TO app_email_jobs;
    GRANT EXECUTE ON FUNCTION public.preparar_avisos_email_piloto(uuid,uuid,timestamptz) TO app_email_jobs;
    GRANT EXECUTE ON FUNCTION public.reservar_entrega_aviso_email_piloto(uuid,uuid,timestamptz) TO app_email_jobs;
    GRANT EXECUTE ON FUNCTION public.resolver_entrega_aviso_email_piloto(uuid,text,text) TO app_email_jobs;
END
$guard$;
