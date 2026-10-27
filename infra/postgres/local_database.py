"""SQLAlchemy y Alembic desde WSL contra el Supabase local, sin mostrar URLs."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tomllib

from local_roles import ROOT, LocalError, load_passwords

API_DIR = ROOT / "apps/api"
sys.path.insert(0, str(API_DIR))

from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

from app.db.connection import (
    MIGRATOR, RUNTIME, DatabaseAccessError, DatabaseConfigurationError,
    create_migration_engine, create_runtime_engine, validate_connection,
)


def local_urls(root=ROOT, environ=None):
    passwords = load_passwords(root / ".env.roles.local", environ=environ)
    try:
        config = tomllib.loads((root / "supabase/config.toml").read_text(encoding="utf8"))
        port = config["db"]["port"]
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError()
    except (OSError, ValueError, KeyError) as error:
        raise LocalError("Revisar db.port en supabase/config.toml.") from error
    return {
        role: URL.create("postgresql+psycopg", username=role,
                         password=passwords[role], host="127.0.0.1", port=port,
                         database="postgres", query={"sslmode": "disable"})
        for role in (MIGRATOR, RUNTIME)
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "alembic"))
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        if args.action == "alembic" and (
            not args.arguments or args.arguments[0] not in
            {"current", "revision", "upgrade", "check", "history", "heads", "show"}
        ):
            raise LocalError("Elegir un comando de Alembic del procedimiento local: current, revision, upgrade, check, history, heads o show.")
        if args.action == "check" and args.arguments:
            raise LocalError("La comprobacion de conexiones no recibe argumentos adicionales.")
        urls = local_urls()
        if args.action == "check":
            for role, factory in ((MIGRATOR, create_migration_engine), (RUNTIME, create_runtime_engine)):
                engine = factory(urls[role])
                try:
                    with engine.connect() as connection:
                        validate_connection(connection, role)
                    print(f"OK: SQLAlchemy conecta como {role}, con esquema public y permisos esperados.")
                finally:
                    engine.dispose()
            return 0
        env = os.environ.copy()
        env["MIGRATION_DATABASE_URL"] = urls[MIGRATOR].render_as_string(hide_password=False)
        # Alembic recibe exclusivamente la URL de migracion, sin fallback runtime.
        env.pop("DATABASE_URL", None)
        return subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(API_DIR / "alembic.ini"), *args.arguments],
            cwd=API_DIR, env=env, check=False,
        ).returncode
    except (LocalError, DatabaseConfigurationError, DatabaseAccessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
    except (SQLAlchemyError, OSError):
        print("ERROR: no se pudo completar la conexion local. Revisar Supabase, roles y credenciales.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
