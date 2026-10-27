"""URLs separadas e identidad efectiva comprobada antes de usar la base."""

import os
import re

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.pool import NullPool

MIGRATOR = "app_migrator"
RUNTIME = "app_runtime"


class DatabaseConfigurationError(RuntimeError):
    pass


class DatabaseAccessError(RuntimeError):
    pass


def database_url(value, role):
    """Validar sin registrar la URL ni interpolar su contraseña en un INI."""
    if role not in (MIGRATOR, RUNTIME):
        raise DatabaseConfigurationError("Rol de conexion desconocido.")
    try:
        url = make_url(value)
        expected_user = rf"{role}(?:\.[A-Za-z0-9_-]+)?"
        if (url.drivername != "postgresql+psycopg"
                or not re.fullmatch(expected_user, url.username or "")
                or not url.host or not url.database or not url.password):
            raise ValueError()
        return url
    except (ArgumentError, TypeError, ValueError) as error:
        raise DatabaseConfigurationError(
            f"Configurar una URL postgresql+psycopg con el usuario {role}, host, base y contraseña."
        ) from error


def create_migration_engine(url=None):
    parsed = database_url(url or os.getenv("MIGRATION_DATABASE_URL", ""), MIGRATOR)
    return create_engine(parsed, poolclass=NullPool, hide_parameters=True,
                         connect_args={"connect_timeout": 10})


def create_runtime_engine(url=None):
    parsed = database_url(url or os.getenv("DATABASE_URL", ""), RUNTIME)
    return create_engine(parsed, pool_pre_ping=True, hide_parameters=True,
                         connect_args={"connect_timeout": 10})


def validate_connection(connection, role):
    """La URL orienta; PostgreSQL confirma el rol y los permisos efectivos."""
    if role not in (MIGRATOR, RUNTIME):
        raise DatabaseConfigurationError("Rol de conexion desconocido.")
    row = connection.execute(text("""
        SELECT session_user AS session_user, current_user AS current_user,
            current_database() AS database, current_schema() AS schema,
            r.rolcanlogin AS login, r.rolsuper AS superuser,
            r.rolcreatedb AS createdb, r.rolcreaterole AS createrole,
            r.rolreplication AS replication, r.rolbypassrls AS bypassrls,
            has_database_privilege(current_user, current_database(), 'CONNECT') AS connect,
            has_database_privilege(current_user, current_database(), 'CREATE') AS create_schema,
            has_schema_privilege(current_user, 'public', 'USAGE') AS usage_public,
            has_schema_privilege(current_user, 'public', 'CREATE') AS create_public,
            (SELECT count(*) FROM pg_auth_members WHERE member = r.oid) AS memberships
        FROM pg_roles r WHERE r.rolname = current_user
    """)).mappings().one()
    expected = {
        "session_user": role, "current_user": role,
        "database": connection.engine.url.database, "schema": "public",
        "login": True, "superuser": False, "createdb": False,
        "createrole": False, "replication": False, "bypassrls": False,
        "connect": True, "create_schema": False, "usage_public": True,
        "create_public": role == MIGRATOR, "memberships": 0,
    }
    mismatches = [name for name, value in expected.items() if row[name] != value]
    if connection.dialect.default_schema_name != "public":
        mismatches.append("default_schema_name")
    if mismatches:
        raise DatabaseAccessError(
            f"La conexion de {role} no cumple el contrato; revisar: {', '.join(mismatches)}."
        )
    return dict(row)
