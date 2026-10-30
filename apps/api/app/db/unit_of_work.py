"""Una sesión y una transacción con identidad explícita por operación."""
from contextlib import contextmanager
from collections.abc import Iterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.connection import RUNTIME, validate_connection


class InvalidDatabaseContext(ValueError):
    pass


def _uuid(value: UUID | str, field: str) -> str:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, str):
        try:
            return str(UUID(value))
        except ValueError:
            pass
    # No incluir el valor recibido: puede contener datos ajenos al contrato.
    raise InvalidDatabaseContext(f"{field} debe ser un UUID valido.")


@contextmanager
def runtime_transaction(
    engine: Engine, *, usuario_id: UUID | str, espacio_id: UUID | str | None = None,
) -> Iterator[Session]:
    """Recibe identidad ya autenticada; no autentica ni comprueba membresías.

    El bloque confirma al salir normalmente y revierte ante una excepción.
    No llamar commit/rollback/begin desde repositorios ni compartir la sesión.
    Materializar resultados dentro del bloque, sin consultas diferidas afuera.
    """
    user = _uuid(usuario_id, "usuario_id")
    workspace = "" if espacio_id is None else _uuid(espacio_id, "espacio_id")
    with Session(engine, autobegin=False, close_resets_only=False) as session:
        with session.begin():
            validate_connection(session.connection(), RUNTIME)
            session.execute(text("""
                SELECT set_config('app.user_id', :usuario_id, true),
                       set_config('app.workspace_id', :espacio_id, true)
            """), {"usuario_id": user, "espacio_id": workspace})
            yield session
