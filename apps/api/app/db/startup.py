"""Conexion opcional de runtime, comprobada antes de aceptar peticiones."""

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import ssl

from sqlalchemy.engine import URL
from starlette.concurrency import run_in_threadpool

from app.db.connection import RUNTIME, create_runtime_engine, validate_connection
from app.db.connection import DatabaseAccessError, DatabaseConfigurationError

logger = logging.getLogger("uvicorn.error")
FIELDS = ("APP_DB_HOST", "APP_DB_USER", "APP_DB_PASSWORD", "APP_DB_CA_FILE")


class RuntimeConfigurationError(ValueError):
    """Solo mensajes construidos con nombres de variables, nunca sus valores."""


def configured_url(env):
    enabled = env.get("APP_DB_ENABLED", "false")
    if enabled not in ("true", "false"):
        raise RuntimeConfigurationError("APP_DB_ENABLED debe ser true o false.")
    if enabled == "false":
        if any(env.get(key) for key in FIELDS):
            raise RuntimeConfigurationError("Hay configuracion de base pero APP_DB_ENABLED no es true.")
        return None
    missing = [key for key in FIELDS if not env.get(key)]
    if missing:
        raise RuntimeConfigurationError("Faltan variables: " + ", ".join(missing))
    if not Path(env["APP_DB_CA_FILE"]).is_file():
        raise RuntimeConfigurationError("No existe el archivo indicado por APP_DB_CA_FILE.")
    return URL.create(
        "postgresql+psycopg", username=env["APP_DB_USER"],
        password=env["APP_DB_PASSWORD"], host=env["APP_DB_HOST"],
        port=5432, database="postgres",
        query={"sslmode": "verify-full", "sslrootcert": env["APP_DB_CA_FILE"]},
    )


def validate_certificate(url):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=url.query["sslrootcert"])


def safe_diagnostic(error, phase):
    if isinstance(error, RuntimeConfigurationError):
        return "CONFIGURACION: " + str(error)
    if phase == "certificado":
        return "CERTIFICADO: comprobar PEM completo y permisos de lectura del Secret File."
    if isinstance(error, DatabaseConfigurationError):
        return "CONFIGURACION_ROL: APP_DB_USER debe identificar app_runtime."
    if isinstance(error, DatabaseAccessError):
        return "PERMISOS: la conexion existe pero el rol efectivo no cumple el contrato."
    original = getattr(error, "orig", error)
    state = getattr(original, "sqlstate", None)
    if state in ("28P01", "28000"):
        return "AUTENTICACION: el servidor rechazo las credenciales o el acceso."
    # Algunos fallos de conexion de libpq no traen SQLSTATE. Clasificar el
    # texto internamente, pero nunca devolverlo ni registrarlo.
    message = str(original).lower()
    if "password authentication failed" in message:
        return "AUTENTICACION: el servidor rechazo las credenciales."
    if "certificate verify failed" in message or "does not match host name" in message:
        return "TLS: fallo la verificacion del certificado del servidor."
    if "could not translate host name" in message or "name or service not known" in message:
        return "DNS: no se pudo resolver el servidor configurado."
    if "timeout expired" in message or "connection timed out" in message:
        return "TIEMPO_AGOTADO: no se completo la conexion en el plazo previsto."
    return "FALLO: etapa=" + phase + "; revisar configuracion y disponibilidad."


def connect_runtime(env):
    engine = None
    phase = "configuracion"
    try:
        url = configured_url(env)
        if url is None:
            return None
        phase = "certificado"
        validate_certificate(url)
        phase = "crear_engine"
        engine = create_runtime_engine(url)
        phase = "conexion"
        with engine.connect() as connection:
            phase = "permisos"
            validate_connection(connection, RUNTIME)
        phase = "cerrar_comprobacion"
        return engine
    except Exception as error:
        diagnostic = safe_diagnostic(error, phase)
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass  # No reemplazar el diagnostico ni revelar errores del driver.
        # No incluir excepciones del driver: pueden contener parametros sensibles.
        raise RuntimeError(
            "Base runtime: " + diagnostic
        ) from None


@asynccontextmanager
async def lifespan(app):
    engine = await run_in_threadpool(connect_runtime, os.environ)
    app.state.runtime_engine = engine
    logger.info("Base runtime: %s", "app_runtime verificado" if engine is not None else "deshabilitada")
    try:
        yield
    finally:
        if engine is not None:
            await run_in_threadpool(engine.dispose)
        app.state.runtime_engine = None
