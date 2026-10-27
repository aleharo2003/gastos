-- Ejecutar con psql -X -v ON_ERROR_STOP=1 -f, como administrador.
-- El programa local_roles.py entrega las contraseñas por stdin a \password.
-- Este archivo no se ejecuta desde el SQL Editor ni desde Alembic.
\set ON_ERROR_STOP on
\set ECHO none
\set VERBOSITY terse
\set SHOW_CONTEXT never

BEGIN;
SET LOCAL search_path = pg_catalog;
SET LOCAL password_encryption = 'scram-sha-256';

DO $bootstrap$
DECLARE
    target text;
    existing pg_roles%ROWTYPE;
    runtime_oid oid;
    migrator_oid oid;
BEGIN
    IF NOT EXISTS (
        SELECT FROM pg_roles
        WHERE rolname = current_user AND (rolsuper OR rolcreaterole)
    ) THEN
        RAISE EXCEPTION 'La conexion administrativa necesita CREATEROLE.';
    END IF;

    FOREACH target IN ARRAY ARRAY['app_migrator', 'app_runtime'] LOOP
        SELECT * INTO existing FROM pg_roles WHERE rolname = target;
        IF FOUND THEN
            IF existing.rolsuper OR existing.rolbypassrls OR existing.rolcreatedb
                OR existing.rolcreaterole OR existing.rolreplication
                OR NOT existing.rolcanlogin THEN
                RAISE EXCEPTION 'El rol % ya existe con atributos incompatibles; revisar antes de continuar.', target;
            END IF;
        ELSE
            EXECUTE format(
                'CREATE ROLE %I LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION',
                target
            );
        END IF;
    END LOOP;

    SELECT oid INTO runtime_oid FROM pg_roles WHERE rolname = 'app_runtime';
    SELECT oid INTO migrator_oid FROM pg_roles WHERE rolname = 'app_migrator';

    -- La membresia administrativa del creador hacia estos roles es esperable.
    -- Lo que se rechaza es que un rol de aplicacion sea miembro de otro rol.
    IF EXISTS (SELECT FROM pg_auth_members WHERE member IN (runtime_oid, migrator_oid)) THEN
        RAISE EXCEPTION 'Los roles de aplicacion no deben ser miembros de otros roles.';
    END IF;

    IF EXISTS (
        SELECT FROM pg_shdepend
        WHERE refclassid = 'pg_authid'::regclass
            AND refobjid = runtime_oid AND deptype = 'o'
    ) THEN
        RAISE EXCEPTION 'app_runtime es propietario de objetos; revisar antes de continuar.';
    END IF;

    IF EXISTS (SELECT FROM pg_namespace WHERE nspowner = migrator_oid AND nspname <> 'public')
        OR EXISTS (
            SELECT FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relowner = migrator_oid AND n.nspname <> 'public'
                -- PostgreSQL crea TOAST y su indice para columnas como text.
                -- Solo se admiten si pertenecen a una relacion propia en public.
                AND NOT (
                    n.nspname = 'pg_toast' AND EXISTS (
                        SELECT FROM pg_class parent
                        LEFT JOIN pg_index toast_index
                            ON toast_index.indrelid = parent.reltoastrelid
                        WHERE parent.relnamespace = 'public'::regnamespace
                            AND parent.relowner = migrator_oid
                            AND (c.oid = parent.reltoastrelid
                                OR c.oid = toast_index.indexrelid)
                    )
                )
        ) THEN
        RAISE EXCEPTION 'app_migrator tiene objetos fuera de public; revisar antes de continuar.';
    END IF;

    IF has_database_privilege('app_runtime', current_database(), 'CREATE')
        OR EXISTS (
            SELECT FROM pg_namespace
            WHERE nspname !~ '^pg_(toast_)?temp_'
                AND has_schema_privilege('app_runtime', oid, 'CREATE')
        ) THEN
        RAISE EXCEPTION 'app_runtime tiene CREATE efectivo; revisar sus grants y los de PUBLIC.';
    END IF;

    EXECUTE format('GRANT CONNECT ON DATABASE %I TO app_migrator, app_runtime', current_database());
    GRANT USAGE ON SCHEMA public TO app_migrator, app_runtime;
    GRANT CREATE ON SCHEMA public TO app_migrator;

    -- Alembic interpreta None como esquema predeterminado: debe ser public.
    EXECUTE format('ALTER ROLE app_migrator IN DATABASE %I SET search_path = public', current_database());
    EXECUTE format('ALTER ROLE app_runtime IN DATABASE %I SET search_path = public', current_database());
END
$bootstrap$;

-- psql cifra en el cliente antes de enviar ALTER ROLE al servidor.
-- Cada comando lee dos lineas de stdin: contraseña y confirmacion.
\password app_migrator
\password app_runtime

COMMIT;
\echo OK: provision de roles completada.
