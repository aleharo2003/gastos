import unittest

from sqlalchemy import Column, ForeignKey, Integer, MetaData, Table

from app.db.migration_metadata import comparison_metadata


class ComparisonMetadataTests(unittest.TestCase):
    def test_normalizes_default_schema_and_fk_without_mutating_models(self):
        source = MetaData(schema='public')
        Table('espacios', source, Column('id', Integer, primary_key=True))
        Table('miembros', source, Column('espacio_id', ForeignKey('public.espacios.id')))
        result = comparison_metadata(source)
        fk = next(iter(result.tables['miembros'].foreign_keys))
        self.assertIsNone(fk.column.table.schema)
        self.assertEqual(fk.column.table.name, 'espacios')
        self.assertEqual(source.tables['public.miembros'].schema, 'public')
        self.assertEqual(next(iter(source.tables['public.miembros'].foreign_keys)).target_fullname,
                         'public.espacios.id')

    def test_preserves_external_fk_target_and_external_table_schema(self):
        source = MetaData(schema='public')
        Table('users', source, Column('id', Integer, primary_key=True), schema='auth')
        Table('perfiles', source, Column('id', ForeignKey('auth.users.id'), primary_key=True))
        result = comparison_metadata(source)
        self.assertEqual(result.tables['auth.users'].schema, 'auth')
        self.assertEqual(next(iter(result.tables['perfiles'].foreign_keys)).column.table.schema, 'auth')

    def test_default_schema_models_remain_default(self):
        source = MetaData()
        Table('entidad', source, Column('id', Integer, primary_key=True))
        self.assertIsNone(comparison_metadata(source).tables['entidad'].schema)


if __name__ == '__main__':
    unittest.main()
