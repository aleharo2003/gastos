"""Limita autogenerate a public, incluido el esquema predeterminado validado."""

from sqlalchemy import ForeignKey, Table
from sqlalchemy.exc import InvalidRequestError


OWNED_SCHEMAS = frozenset((None, 'public'))
VERSION_TABLE = 'alembic_version'


def include_name(name, type_, parent_names):
    """Descarta esquemas externos antes de reflejar sus tablas."""
    if type_ == 'schema':
        return name in OWNED_SCHEMAS
    if type_ == 'table' and name == VERSION_TABLE:
        # El esquema predeterminado se refleja como None aunque la tabla de
        # version se configure expresamente en public. Nunca proponer su DROP.
        return False
    return 'schema_name' in parent_names and parent_names['schema_name'] in OWNED_SCHEMAS


def include_object(object_, name, type_, reflected, compare_to):
    """Usa la tabla propietaria, tanto en reflexión como en MetaData."""
    try:
        if isinstance(object_, Table):
            table = object_
        elif isinstance(object_, ForeignKey):
            # La FK pertenece a su columna local, no a la tabla referenciada.
            table = object_.parent.table if object_.parent is not None else None
        else:
            table = getattr(object_, 'table', None)
    except InvalidRequestError:
        # Un objeto todavía sin asociar a una tabla no tiene alcance definido.
        return False
    return (isinstance(table, Table)
            and table.schema in OWNED_SCHEMAS
            and table.name != VERSION_TABLE)
