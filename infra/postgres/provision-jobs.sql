-- Administrador, despues de Alembic 0017. psql -X --file (no SQL Editor).
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
    IF to_regprocedure('public.generar_cuotas_mes()') IS NULL THEN
        RAISE EXCEPTION 'Aplicar primero la migracion 0017.';
    END IF;
    SELECT * INTO r FROM pg_roles WHERE rolname='app_jobs';
    IF NOT FOUND THEN
        CREATE ROLE app_jobs LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
        SELECT * INTO r FROM pg_roles WHERE rolname='app_jobs';
    END IF;
    IF r.rolsuper OR r.rolbypassrls OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication
        OR r.rolinherit OR NOT r.rolcanlogin
        OR EXISTS (SELECT FROM pg_auth_members WHERE member=r.oid)
        OR EXISTS (SELECT FROM pg_shdepend WHERE refclassid='pg_authid'::regclass AND refobjid=r.oid AND deptype='o')
    THEN RAISE EXCEPTION 'app_jobs tiene atributos, membresias u objetos incompatibles.'; END IF;
    IF has_database_privilege('app_jobs',current_database(),'CREATE')
        OR EXISTS (SELECT FROM pg_namespace WHERE nspname !~ '^pg_(toast_)?temp_'
            AND has_schema_privilege('app_jobs',oid,'CREATE'))
        OR EXISTS (SELECT FROM pg_class WHERE relnamespace='public'::regnamespace
            AND relkind IN ('r','p','v','m','f')
            AND (has_table_privilege('app_jobs',oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                OR has_any_column_privilege('app_jobs',oid,'SELECT,INSERT,UPDATE,REFERENCES')))
        OR EXISTS (SELECT FROM pg_proc WHERE proowner='app_migrator'::regrole
            AND oid<>'public.generar_cuotas_mes()'::regprocedure
            AND has_function_privilege('app_jobs',oid,'EXECUTE'))
    THEN RAISE EXCEPTION 'app_jobs tiene permisos de datos o DDL incompatibles.'; END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO app_jobs',current_database());
    GRANT USAGE ON SCHEMA public TO app_jobs;
    GRANT EXECUTE ON FUNCTION public.generar_cuotas_mes() TO app_jobs;
    EXECUTE format('ALTER ROLE app_jobs IN DATABASE %I SET search_path=public',current_database());
END
$setup$;
\password app_jobs
COMMIT;
\echo OK: rol de generacion mensual preparado.
