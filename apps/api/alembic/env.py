from logging.config import fileConfig

from alembic import context
from alembic.util import CommandError
from sqlalchemy.exc import SQLAlchemyError

from app.db.base import Base
from app.db.migration_metadata import comparison_metadata
from app.db.connection import (
    MIGRATOR, DatabaseAccessError, DatabaseConfigurationError,
    create_migration_engine, validate_connection,
)
from app.db.models import Espacio  # noqa: F401: registra el modelo en MetaData
from app.db.schema_filters import include_name, include_object

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)


def apply_migrations(connection):
    validate_connection(connection, MIGRATOR)
    context.configure(
        connection=connection,
        target_metadata=comparison_metadata(Base.metadata),
        include_schemas=True,
        include_name=include_name,
        include_object=include_object,
        version_table_schema="public",
        compare_type=True,
        compare_server_default=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations():
    if context.is_offline_mode():
        raise CommandError("Este incremento requiere conexion para comprobar el rol y el esquema antes de migrar.")
    engine = None
    try:
        supplied = config.attributes.get("connection")
        if supplied is not None:
            # El runner es propietario de la transaccion: upgrade y check
            # deben aprobar antes de confirmar. No cerrar esta conexion aqui.
            if not supplied.in_transaction():
                raise CommandError("La conexion compartida requiere una transaccion activa.")
            apply_migrations(supplied)
        else:
            engine = create_migration_engine()
            with engine.begin() as connection:
                apply_migrations(connection)
    except (DatabaseConfigurationError, DatabaseAccessError) as error:
        raise CommandError(str(error)) from None
    except SQLAlchemyError:
        raise CommandError("No se pudo completar la operacion de migraciones; revisar conexion, revision y permisos.") from None
    finally:
        if engine is not None:
            engine.dispose()


run_migrations()
