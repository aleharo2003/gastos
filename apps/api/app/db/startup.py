"""Conexion opcional de runtime, comprobada antes de aceptar peticiones."""

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path

from sqlalchemy.engine import URL
from starlette.concurrency import run_in_threadpool

from app.db.connection import RUNTIME, create_runtime_engine, validate_connection

logger = logging.getLogger("uvicorn.error")
FIELDS = ("APP_DB_HOST", "APP_DB_USER", "APP_DB_PASSWORD", "APP_DB_CA_FILE")


def configured_url(env):
    enabled = env.get("APP_DB_ENABLED", "false")
    if enabled not in ("true", "false"):
        raise ValueError("APP_DB_ENABLED debe ser true o false.")
    if enabled == "false":
        if any(env.get(key) for key in FIELDS):
            raise ValueError("Hay configuracion de base pero APP_DB_ENABLED no es true.")
        return None
    if not all(env.get(key) for key in FIELDS):
        raise ValueError("Falta configuracion de runtime.")
    if not Path(env["APP_DB_CA_FILE"]).is_file():
        raise ValueError("Falta el archivo del certificado.")
    return URL.create(
        "postgresql+psycopg", username=env["APP_DB_USER"],
        password=env["APP_DB_PASSWORD"], host=env["APP_DB_HOST"],
        port=5432, database="postgres",
        query={"sslmode": "verify-full", "sslrootcert": env["APP_DB_CA_FILE"]},
    )


def connect_runtime(env):
    engine = None
    try:
        url = configured_url(env)
        if url is None:
            return None
        engine = create_runtime_engine(url)
        with engine.connect() as connection:
            validate_connection(connection, RUNTIME)
        return engine
    except Exception:
        if engine is not None:
            engine.dispose()
        # No incluir excepciones del driver: pueden contener parametros sensibles.
        raise RuntimeError(
            "No se pudo validar la conexion app_runtime; revisar configuracion, TLS y permisos."
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
