-- Administrador, despues de Alembic 0028. psql -X --file (no SQL Editor).
\set ON_ERROR_STOP on
\set ECHO none
\set VERBOSITY terse
\set SHOW_CONTEXT never
BEGIN;
SET LOCAL search_path=pg_catalog;
SET LOCAL password_encryption='scram-sha-256';
DO $setup$
DECLARE r pg_roles%ROWTYPE;
BEGIN
    IF to_regprocedure('public.previsualizar_avisos_email_piloto(uuid,uuid,timestamptz)') IS NULL THEN
        RAISE EXCEPTION 'Aplicar primero la migracion 0028.';
    END IF;
    SELECT * INTO r FROM pg_roles WHERE rolname='app_email_jobs';
    IF NOT FOUND THEN
        CREATE ROLE app_email_jobs LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
        SELECT * INTO r FROM pg_roles WHERE rolname='app_email_jobs';
    END IF;
    IF r.rolsuper OR r.rolbypassrls OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication
        OR r.rolinherit OR NOT r.rolcanlogin
        OR EXISTS (SELECT FROM pg_auth_members WHERE member=r.oid)
        OR EXISTS (SELECT FROM pg_shdepend WHERE refclassid='pg_authid'::regclass AND refobjid=r.oid AND deptype='o')
    THEN RAISE EXCEPTION 'app_email_jobs tiene atributos, membresias u objetos incompatibles.'; END IF;
    IF has_database_privilege('app_email_jobs',current_database(),'CREATE')
        OR EXISTS (SELECT FROM pg_namespace WHERE nspname !~ '^pg_(toast_)?temp_'
            AND has_schema_privilege('app_email_jobs',oid,'CREATE'))
        OR EXISTS (SELECT FROM pg_class WHERE relnamespace='public'::regnamespace
            AND relkind IN ('r','p','v','m','f')
            AND (has_table_privilege('app_email_jobs',oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                OR has_any_column_privilege('app_email_jobs',oid,'SELECT,INSERT,UPDATE,REFERENCES')))
        OR EXISTS (SELECT FROM pg_proc WHERE proowner='app_migrator'::regrole
            AND oid NOT IN ('public.previsualizar_avisos_email_piloto(uuid,uuid,timestamptz)'::regprocedure,
                'public.encolar_avisos_email_piloto(uuid,uuid,timestamptz)'::regprocedure,
                'public.preparar_avisos_email_piloto(uuid,uuid,timestamptz)'::regprocedure,
                'public.reservar_entrega_aviso_email_piloto(uuid,uuid,timestamptz)'::regprocedure,
                'public.resolver_entrega_aviso_email_piloto(uuid,text,text)'::regprocedure)
            AND NOT EXISTS (
                SELECT FROM unnest(ARRAY[
                    to_regprocedure('public.resumen_semanal_piloto(uuid,uuid,timestamptz)'),
                    to_regprocedure('public.reservar_resumen_semanal_piloto(uuid,uuid,timestamptz,uuid)'),
                    to_regprocedure('public.resolver_resumen_semanal_piloto(uuid,text)')
                ]) AS permitida(funcion) WHERE permitida.funcion=pg_proc.oid
            )
            AND has_function_privilege('app_email_jobs',oid,'EXECUTE'))
    THEN RAISE EXCEPTION 'app_email_jobs tiene permisos de datos o DDL incompatibles.'; END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO app_email_jobs',current_database());
    GRANT USAGE ON SCHEMA public TO app_email_jobs;
    EXECUTE format('ALTER ROLE app_email_jobs IN DATABASE %I SET search_path=public',current_database());
END
$setup$;
\password app_email_jobs
COMMIT;
\echo OK: rol del piloto de correo preparado.
