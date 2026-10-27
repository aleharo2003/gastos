"""Reconstruye y prueba una base Supabase desechable, separada del desarrollo."""

from contextlib import ExitStack
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/postgres"))
sys.path.insert(0, str(ROOT / "apps/api"))

from local_roles import LocalDatabase, LocalError
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.db.connection import (
    MIGRATOR, RUNTIME, create_migration_engine, create_runtime_engine,
    validate_connection,
)

CLI = ["npx", "--yes", "supabase@2.121.0"]
# Esta prueba necesita el PostgreSQL de Supabase, no sus servidores HTTP.
EXCLUDED = "gotrue,realtime,storage-api,imgproxy,kong,mailpit,postgrest,postgres-meta,studio,edge-runtime,logflare,vector,supavisor"
PORT_SETTING = re.compile(r"^(\s*(?:port|shadow_port|smtp_port|pop3_port|inspector_port)\s*=\s*)\d+", re.MULTILINE)


class CheckError(RuntimeError):
    pass


def step(label):
    print(label, flush=True)


def run(command, *, cwd=ROOT, env=None, timeout=120):
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=timeout, check=False)


def checked(label, command, **kwargs):
    result = run(command, **kwargs)
    if result.returncode:
        # No volcar stdout/stderr: el CLI puede incluir URLs y claves locales.
        raise CheckError(f"{label} fallo (codigo {result.returncode}).")
    return result


def make_config(source, project, ports):
    if not re.fullmatch(r"gastos-ci-[a-f0-9]{16}", project):
        raise CheckError("Identificador temporal invalido.")
    source, count = re.subn(r'^project_id\s*=\s*"[^"\n]+"',
                            f'project_id = "{project}"', source, count=1,
                            flags=re.MULTILINE)
    if count != 1:
        raise CheckError("Falta project_id en la configuracion.")
    source = PORT_SETTING.sub(lambda match: match.group(1) + str(next(ports)), source)
    source, count = re.subn(r'(\[db\.seed\][^\[]*?^enabled\s*=\s*)true',
                            r'\g<1>false', source, count=1,
                            flags=re.MULTILINE)
    if count != 1:
        raise CheckError("Revisar db.seed en la configuracion versionada.")
    config = tomllib.loads(source)
    if config["project_id"] != project or config["db"]["seed"]["enabled"]:
        raise CheckError("Configuracion temporal invalida.")
    return source, config["db"]["port"]


def free_ports(count):
    # Reservarlos juntos evita repetir un puerto dentro de la configuracion.
    with ExitStack() as stack:
        sockets = [stack.enter_context(socket.socket()) for _ in range(count)]
        for item in sockets:
            item.bind(("127.0.0.1", 0))
        return [item.getsockname()[1] for item in sockets]


@dataclass
class Fixture:
    workdir: Path
    project: str
    port: int

    @property
    def container(self):
        return f"supabase_db_{self.project}"

    def cli(self, *arguments):
        return [*CLI, "--workdir", str(self.workdir), *arguments]

    def guard(self):
        config_path = self.workdir / "supabase/config.toml"
        if (not self.workdir.name.startswith("gastos-db-ci-")
                or not re.fullmatch(r"gastos-ci-[a-f0-9]{16}", self.project)
                or tomllib.loads(config_path.read_text())["project_id"] != self.project):
            raise CheckError("El destino no es la fixture temporal creada por esta prueba.")


def admin(database, sql):
    # Solo las fixtures externas requieren el administrador interno local.
    # La provision sigue usando postgres; Alembic usa app_migrator.
    result = database.psql("supabase_admin", sql)
    if result.returncode:
        raise CheckError("Fallo una operacion administrativa en la fixture temporal.")
    return result.stdout.strip()


def verify_container(fixture):
    result = checked("Identidad del contenedor temporal",
                     ["docker", "inspect", "--format", "{{json .Config.Labels}}",
                      fixture.container])
    labels = json.loads(result.stdout) or {}
    if labels.get("com.supabase.cli.project") != fixture.project:
        raise CheckError("El contenedor no pertenece al proyecto temporal.")


def external_state(database):
    # Estructura de relaciones y columnas externas, mas datos centinela.
    return json.loads(admin(database, """
        SELECT json_build_object(
          'relations', (SELECT json_agg(x ORDER BY x.schema, x.name) FROM (
            SELECT n.nspname AS schema, c.relname AS name, c.oid, c.relkind,
              (SELECT json_agg(json_build_array(a.attname, a.atttypid, a.attnotnull)
                       ORDER BY a.attnum)
               FROM pg_attribute a WHERE a.attrelid=c.oid AND a.attnum>0
                 AND NOT a.attisdropped) AS columns
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname <> 'public' AND n.nspname <> 'information_schema'
              AND n.nspname !~ '^pg_'
          ) x),
          'auth', (SELECT valor FROM auth.gastos_ci_sentinel WHERE id=1),
          'storage', (SELECT valor FROM storage.gastos_ci_sentinel WHERE id=1),
          'unknown', (SELECT valor FROM gastos_ci_external.sentinel WHERE id=1)
        );
    """))


def alembic(arguments, migration_url):
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    env["MIGRATION_DATABASE_URL"] = migration_url.render_as_string(hide_password=False)
    return run([sys.executable, "-m", "alembic", "-c",
                str(ROOT / "apps/api/alembic.ini"), *arguments], env=env)


def require_alembic(arguments, url):
    result = alembic(arguments, url)
    if result.returncode:
        raise CheckError(f"Alembic {' '.join(arguments)} fallo (codigo {result.returncode}).")


def require_drift(result):
    output = result.stdout + result.stderr
    if (result.returncode == 0 or "New upgrade operations detected" not in output
            or "gastos_ci_unversioned" not in output):
        raise CheckError("alembic check no detecto la tabla publica sin migracion.")


def check_database(fixture):
    database = LocalDatabase(fixture.container)
    passwords = {role: secrets.token_urlsafe(32) for role in (MIGRATOR, RUNTIME)}
    step("3/8 Crear los roles y verificar autenticacion y permisos efectivos.")
    database.provision(passwords)
    database.check(passwords)
    urls = {role: URL.create("postgresql+psycopg", username=role,
                            password=passwords[role], host="127.0.0.1",
                            port=fixture.port, database="postgres",
                            query={"sslmode": "disable"})
            for role in (MIGRATOR, RUNTIME)}
    engines = {MIGRATOR: create_migration_engine(urls[MIGRATOR]),
               RUNTIME: create_runtime_engine(urls[RUNTIME])}
    try:
        for role, engine in engines.items():
            with engine.connect() as connection:
                validate_connection(connection, role)
        # Fixtures creadas por el administrador solo en esta base desechable.
        admin(database, """
            CREATE SCHEMA IF NOT EXISTS auth;
            CREATE SCHEMA IF NOT EXISTS storage;
            CREATE SCHEMA gastos_ci_external;
            CREATE TABLE auth.gastos_ci_sentinel (id integer PRIMARY KEY, valor text);
            CREATE TABLE storage.gastos_ci_sentinel (id integer PRIMARY KEY, valor text);
            CREATE TABLE gastos_ci_external.sentinel (id integer PRIMARY KEY, valor text);
            INSERT INTO auth.gastos_ci_sentinel VALUES (1, 'conservar-auth');
            INSERT INTO storage.gastos_ci_sentinel VALUES (1, 'conservar-storage');
            INSERT INTO gastos_ci_external.sentinel VALUES (1, 'conservar-desconocido');
        """)
        before = external_state(database)
        step("4/8 Aplicar todas las migraciones versionadas como app_migrator.")
        require_alembic(["upgrade", "head"], urls[MIGRATOR])
        config = Config(str(ROOT / "apps/api/alembic.ini"))
        heads = set(ScriptDirectory.from_config(config).get_heads())
        with engines[MIGRATOR].connect() as connection:
            actual = set(connection.execute(text("SELECT version_num FROM public.alembic_version")).scalars())
            if not heads or actual != heads:
                raise CheckError("La base no quedo en las revisiones head del repositorio.")
            owner = connection.execute(text("SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='public.espacios'::regclass")).scalar_one()
            if owner != MIGRATOR:
                raise CheckError("espacios no pertenece a app_migrator.")
        step("5/8 Repetir la provision y comprobar que el esquema coincide con los modelos.")
        database.provision(passwords)
        database.check(passwords)
        require_alembic(["check"], urls[MIGRATOR])
        step("6/8 Introducir una tabla sin migracion y exigir que alembic check falle.")
        with engines[MIGRATOR].begin() as connection:
            connection.execute(text("CREATE TABLE public.gastos_ci_unversioned (id integer PRIMARY KEY)"))
        try:
            require_drift(alembic(["check"], urls[MIGRATOR]))
        finally:
            with engines[MIGRATOR].begin() as connection:
                connection.execute(text("DROP TABLE public.gastos_ci_unversioned"))
        require_alembic(["check"], urls[MIGRATOR])
        step("7/8 Comprobar que runtime no puede crear tablas en public.")
        with engines[RUNTIME].connect() as connection:
            try:
                connection.execute(text("CREATE TABLE public.gastos_ci_forbidden (id integer)"))
            except SQLAlchemyError as error:
                if getattr(error.orig, "sqlstate", None) != "42501":
                    raise CheckError("La prueba de runtime fallo por una causa inesperada.") from None
            else:
                raise CheckError("Runtime pudo crear una tabla en public.")
            finally:
                connection.rollback()
        step("8/8 Comparar estructura externa y datos centinela con su estado inicial.")
        if external_state(database) != before:
            raise CheckError("Cambio la estructura externa o sus datos centinela.")
    finally:
        for engine in engines.values():
            engine.dispose()


def main():
    if len(sys.argv) != 1:
        print("Uso: python infra/ci/check_database.py (sin URL ni destino)", file=sys.stderr)
        return 1
    if sys.platform != "linux":
        print("Ejecutar en Ubuntu/WSL o en el runner Linux de GitHub.", file=sys.stderr)
        return 1
    try:
        source = (ROOT / "supabase/config.toml").read_text(encoding="utf8")
        project = "gastos-ci-" + secrets.token_hex(8)
        config, port = make_config(source, project, iter(free_ports(len(PORT_SETTING.findall(source)))))
        checked("Docker", ["docker", "info", "--format", "{{.ServerVersion}}"])
        with tempfile.TemporaryDirectory(prefix="gastos-db-ci-") as directory:
            workdir = Path(directory).resolve()
            (workdir / "supabase").mkdir()
            (workdir / "supabase/config.toml").write_text(config, encoding="utf8")
            fixture = Fixture(workdir, project, port)
            fixture.guard()
            # No reutilizar recursos previos, aunque coincidiera el ID aleatorio.
            existing = checked("Inventario de la fixture", ["docker", "ps", "--all", "--quiet", "--filter", f"label=com.supabase.cli.project={project}"])
            if existing.stdout.strip():
                raise CheckError("El proyecto temporal ya tiene contenedores; no se reutiliza.")
            try:
                step("1/8 Iniciar un PostgreSQL Supabase temporal con CLI 2.121.0.")
                checked("supabase start", fixture.cli("start", "--exclude", EXCLUDED), timeout=600)
                fixture.guard()
                verify_container(fixture)
                step("2/8 Reconstruir solo la base temporal, sin semillas de negocio.")
                checked("supabase db reset --local --no-seed", fixture.cli("db", "reset", "--local", "--no-seed", "--yes"), timeout=240)
                check_database(fixture)
            finally:
                fixture.guard()
                step("Retirar los contenedores y volumenes del proyecto temporal.")
                checked("Limpieza de la fixture", fixture.cli("stop", "--no-backup"), timeout=180)
        step("OK: reconstruccion, roles, migraciones, deteccion de drift y esquemas externos.")
        return 0
    except (CheckError, LocalError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
    except (OSError, ValueError, KeyError, StopIteration, subprocess.TimeoutExpired, SQLAlchemyError):
        print("ERROR: no se pudo completar la comprobacion temporal. Revisar Docker, dependencias y la fase indicada; no mostrar URLs ni contraseñas.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
