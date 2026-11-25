-- Ejecutar con el administrador de roles, mediante psql -X --file.
\set ON_ERROR_STOP on
\set ECHO none
\set VERBOSITY terse
\set SHOW_CONTEXT never
BEGIN;
SET LOCAL search_path=pg_catalog;
SET LOCAL password_encryption='scram-sha-256';
DO $setup$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='app_backup') THEN
        CREATE ROLE app_backup LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles r WHERE r.rolname='app_backup' AND r.rolcanlogin
        AND NOT (r.rolsuper OR r.rolbypassrls OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication OR r.rolinherit)
        AND NOT EXISTS (SELECT FROM pg_auth_members WHERE member=r.oid)
        AND NOT EXISTS (SELECT FROM pg_shdepend WHERE refclassid='pg_authid'::regclass AND refobjid=r.oid AND deptype='o'))
        OR has_database_privilege('app_backup',current_database(),'CREATE')
        OR EXISTS (SELECT FROM pg_namespace WHERE nspname !~ '^pg_(toast_)?temp_'
                   AND has_schema_privilege('app_backup',oid,'CREATE'))
    THEN RAISE EXCEPTION 'app_backup tiene atributos, membresias u objetos incompatibles.'; END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO app_backup',current_database());
    GRANT USAGE ON SCHEMA public TO app_backup;
END
$setup$;
\password app_backup
COMMIT;
