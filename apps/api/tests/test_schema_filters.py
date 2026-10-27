"""Regresiones del alcance de Alembic, sin conexión a una base de datos."""

import unittest

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Table,
    UniqueConstraint,
)

from app.db.schema_filters import include_name, include_object


def table_with_objects(schema):
    metadata = MetaData()
    table = Table(
        'entidad', metadata,
        Column('id', Integer, primary_key=True),
        Column('codigo', Integer, nullable=False),
        UniqueConstraint('codigo', name='uq_entidad_codigo'),
        CheckConstraint('codigo > 0', name='ck_entidad_codigo'),
        schema=schema,
    )
    Index('ix_entidad_codigo', table.c.codigo)
    return table


def objects_of(table):
    yield table, 'table'
    for column in table.columns:
        yield column, 'column'
    for index in table.indexes:
        yield index, 'index'
    for constraint in table.constraints:
        yield constraint, constraint.__visit_name__


class NameFilterTests(unittest.TestCase):
    def test_default_and_public_schema_are_included(self):
        for schema in (None, 'public'):
            with self.subTest(schema=schema):
                self.assertTrue(include_name(schema, 'schema', {}))

    def test_platform_and_unknown_schemas_are_excluded(self):
        for schema in ('auth', 'storage', 'realtime', 'extensions', 'future_platform_schema'):
            with self.subTest(schema=schema):
                self.assertFalse(include_name(schema, 'schema', {}))

    def test_parent_schema_controls_reflected_names(self):
        types = ('table', 'column', 'index', 'unique_constraint', 'foreign_key_constraint')
        for schema in (None, 'public', 'auth', 'future_platform_schema'):
            for type_ in types:
                with self.subTest(schema=schema, type_=type_):
                    parents = {'schema_name': schema, 'table_name': 'entidad'}
                    self.assertEqual(include_name('objeto', type_, parents), schema in (None, 'public'))

    def test_table_absent_from_models_is_still_reflected(self):
        # No tabla blanca por nombre: un desvío en public debe seguir visible.
        for schema in (None, 'public'):
            with self.subTest(schema=schema):
                self.assertTrue(include_name('tabla_que_no_esta_en_modelos', 'table', {'schema_name': schema}))

    def test_names_without_schema_context_are_excluded(self):
        for type_ in ('table', 'column', 'index', 'future_object_type'):
            with self.subTest(type_=type_):
                self.assertFalse(include_name('objeto', type_, {}))

    def test_internal_version_table_is_excluded_for_both_public_aliases(self):
        for schema in (None, 'public'):
            with self.subTest(schema=schema):
                self.assertFalse(include_name('alembic_version', 'table', {'schema_name': schema}))


class ObjectFilterTests(unittest.TestCase):
    def test_internal_version_table_and_its_objects_are_excluded(self):
        for schema in (None, 'public'):
            table = Table('alembic_version', MetaData(),
                          Column('version_num', Integer, primary_key=True), schema=schema)
            for object_, type_ in objects_of(table):
                for reflected in (False, True):
                    with self.subTest(schema=schema, type_=type_, reflected=reflected):
                        self.assertFalse(include_object(object_, object_.name, type_, reflected, None))

    def test_owned_tables_and_associated_objects_are_included_on_both_sides(self):
        for schema in (None, 'public'):
            table = table_with_objects(schema)
            for object_, type_ in objects_of(table):
                for reflected in (False, True):
                    with self.subTest(schema=schema, type_=type_, reflected=reflected):
                        self.assertTrue(include_object(object_, object_.name, type_, reflected, None))

    def test_external_tables_and_associated_objects_are_excluded_on_both_sides(self):
        for schema in ('auth', 'storage', 'realtime', 'extensions', 'future_platform_schema'):
            table = table_with_objects(schema)
            for object_, type_ in objects_of(table):
                for reflected in (False, True):
                    with self.subTest(schema=schema, type_=type_, reflected=reflected):
                        self.assertFalse(include_object(object_, object_.name, type_, reflected, None))

    def test_reflected_public_table_without_model_remains_visible(self):
        table = Table('tabla_sobrante', MetaData(), Column('id', Integer), schema='public')
        self.assertTrue(include_object(table, table.name, 'table', True, None))

    def test_public_foreign_key_to_auth_is_included_but_auxiliary_auth_table_is_not(self):
        metadata = MetaData()
        users = Table('users', metadata, Column('id', Integer, primary_key=True), schema='auth')
        profiles = Table(
            'perfiles', metadata,
            Column('usuario_id', Integer, ForeignKey('auth.users.id'), primary_key=True),
            schema='public',
        )
        constraint = next(iter(profiles.foreign_key_constraints))
        foreign_key = next(iter(profiles.foreign_keys))
        self.assertIs(foreign_key.column.table, users)
        self.assertFalse(include_object(users, users.name, 'table', False, None))
        self.assertFalse(include_object(users.c.id, 'id', 'column', False, None))
        for reflected in (False, True):
            with self.subTest(reflected=reflected):
                self.assertTrue(include_object(constraint, constraint.name, 'foreign_key_constraint', reflected, None))
                self.assertTrue(include_object(foreign_key, foreign_key.name, 'foreign_key', reflected, None))
                self.assertTrue(include_object(profiles.c.usuario_id, 'usuario_id', 'column', reflected, None))

    def test_default_schema_foreign_key_to_auth_is_included(self):
        metadata = MetaData()
        Table('users', metadata, Column('id', Integer, primary_key=True), schema='auth')
        profiles = Table('perfiles', metadata, Column('usuario_id', Integer),
                         ForeignKeyConstraint(['usuario_id'], ['auth.users.id']))
        constraint = next(iter(profiles.foreign_key_constraints))
        self.assertTrue(include_object(constraint, constraint.name, 'foreign_key_constraint', False, None))

    def test_external_foreign_key_to_public_is_excluded(self):
        metadata = MetaData()
        Table('espacios', metadata, Column('id', Integer, primary_key=True), schema='public')
        external = Table(
            'registro', metadata,
            Column('espacio_id', Integer, ForeignKey('public.espacios.id')),
            schema='future_platform_schema',
        )
        constraint = next(iter(external.foreign_key_constraints))
        foreign_key = next(iter(external.foreign_keys))
        self.assertFalse(include_object(constraint, constraint.name, 'foreign_key_constraint', True, None))
        self.assertFalse(include_object(foreign_key, foreign_key.name, 'foreign_key', False, None))

    def test_compare_target_does_not_change_ownership_of_the_object(self):
        public = Table('entidad', MetaData(), Column('id', Integer), schema='public')
        external = Table('entidad', MetaData(), Column('id', Integer), schema='auth')
        self.assertFalse(include_object(external, external.name, 'table', True, public))
        self.assertTrue(include_object(public, public.name, 'table', False, external))

    def test_public_objects_are_not_hidden_by_an_unrelated_metadata_flag(self):
        table = Table('entidad', MetaData(), Column('id', Integer), schema='public',
                      info={'skip_autogenerate': True})
        table.c.id.info['skip_autogenerate'] = True
        self.assertTrue(include_object(table, table.name, 'table', False, None))
        self.assertTrue(include_object(table.c.id, 'id', 'column', False, None))

    def test_objects_without_an_owning_table_are_excluded(self):
        objects = (
            object(),
            Column('id', Integer),
            Index('ix_without_table', 'codigo'),
            UniqueConstraint('codigo'),
            ForeignKeyConstraint(['id'], ['auth.users.id']),
            ForeignKey('auth.users.id'),
        )
        for object_ in objects:
            with self.subTest(type_=type(object_).__name__):
                self.assertFalse(include_object(object_, None, 'unknown', False, None))


if __name__ == '__main__':
    unittest.main()
