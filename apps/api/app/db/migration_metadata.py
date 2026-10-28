"""Representa public como esquema predeterminado solo para comparar migraciones."""
from sqlalchemy import MetaData
from sqlalchemy.schema import BLANK_SCHEMA


def comparison_metadata(source):
    # validate_connection debe haber comprobado public como esquema efectivo.
    # PostgreSQL refleja las FK a public con esquema None. Normalizamos una copia,
    # sin cambiar el MetaData que utiliza la aplicación ni ocultar diferencias.
    result = MetaData(naming_convention=source.naming_convention)

    def referred_schema(table, to_schema, constraint, referred):
        return BLANK_SCHEMA if referred == 'public' else referred

    for table in source.tables.values():
        table.to_metadata(result, schema=None if table.schema == 'public' else table.schema,
                          referred_schema_fn=referred_schema)
    return result
