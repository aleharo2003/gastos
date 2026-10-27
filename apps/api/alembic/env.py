from logging.config import fileConfig

from alembic import context
from alembic.util import CommandError
from sqlalchemy.exc import SQLAlchemyError

from app.db.base import Base
from app.db.connection import (
    MIGRATOR, DatabaseAccessError, DatabaseConfigurationError,
    create_migration_engine, validate_connection,
)
from app.db.models import Espacio  # noqa: F401: registra el modelo en MetaData
from app.db.schema_filters import include_name, include_object

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)


def run_migrations():
    if context.is_offline_mode():
        raise CommandError("Este incremento requiere conexion para comprobar el rol y el esquema antes de migrar.")
    engine = None
    try:
        engine = create_migration_engine()
        with engine.connect() as connection:
            # La comprobacion SELECT y las migraciones comparten una transaccion
            # exterior que se confirma solo al terminar correctamente.
            with connection.begin():
                validate_connection(connection, MIGRATOR)
                context.configure(
                    connection=connection,
                    target_metadata=Base.metadata,
                    include_schemas=True,
                    include_name=include_name,
                    include_object=include_object,
                    version_table_schema="public",
                    compare_type=True,
                    compare_server_default=False,
                )
                with context.begin_transaction():
                    context.run_migrations()
    except (DatabaseConfigurationError, DatabaseAccessError) as error:
        raise CommandError(str(error)) from None
    except SQLAlchemyError:
        raise CommandError("No se pudo completar la operacion de migraciones; revisar conexion, revision y permisos.") from None
    finally:
        if engine is not None:
            engine.dispose()


run_migrations()
