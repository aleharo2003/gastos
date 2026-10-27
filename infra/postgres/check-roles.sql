-- Consulta de metadatos; no crea objetos ni modifica datos.
SELECT json_build_object(
    'session_user', session_user,
    'current_user', current_user,
    'database', current_database(),
    'schema', current_schema(),
    'login', r.rolcanlogin,
    'superuser', r.rolsuper,
    'createdb', r.rolcreatedb,
    'createrole', r.rolcreaterole,
    'replication', r.rolreplication,
    'bypassrls', r.rolbypassrls,
    'connect', has_database_privilege(current_user, current_database(), 'CONNECT'),
    'create_schema', has_database_privilege(current_user, current_database(), 'CREATE'),
    'usage_public', has_schema_privilege(current_user, 'public', 'USAGE'),
    'create_public', has_schema_privilege(current_user, 'public', 'CREATE'),
    'memberships', (SELECT count(*) FROM pg_auth_members WHERE member = r.oid)
)
FROM pg_roles r WHERE rolname = current_user;
