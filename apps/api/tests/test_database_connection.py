"""Contratos de configuración, identidad y modelos sin abrir conexiones."""

import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import UUID

from sqlalchemy import Text, Uuid
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

from app.db import connection as database
from app.db.models import Espacio


PASSWORD = "contraseña de prueba'@%:/\\$-1234"


def url_for(role, *, username=None):
    return URL.create('postgresql+psycopg', username=username or role,
                      password=PASSWORD, host='127.0.0.1', port=54322,
                      database='postgres')


def metadata_for(role):
    return {
        'session_user': role, 'current_user': role, 'database': 'postgres',
        'schema': 'public', 'login': True, 'superuser': False,
        'createdb': False, 'createrole': False, 'replication': False,
        'bypassrls': False, 'connect': True, 'create_schema': False,
        'usage_public': True, 'create_public': role == database.MIGRATOR,
        'memberships': 0,
    }


def connection_for(role, **changes):
    connection = Mock()
    connection.engine = SimpleNamespace(url=url_for(role))
    connection.dialect = SimpleNamespace(default_schema_name='public')
    connection.execute.return_value.mappings.return_value.one.return_value = metadata_for(role) | changes
    return connection


class DatabaseURLTests(unittest.TestCase):
    def test_url_object_preserves_special_characters_without_ini_interpolation(self):
        original = url_for(database.MIGRATOR)
        encoded = original.render_as_string(hide_password=False)
        parsed = database.database_url(encoded, database.MIGRATOR)
        self.assertEqual(parsed.password, PASSWORD)
        self.assertEqual(parsed.host, '127.0.0.1')
        self.assertEqual(parsed.port, 54322)
        self.assertEqual(parsed.database, 'postgres')

    def test_own_role_and_session_pooler_project_suffix_are_accepted(self):
        for role in (database.MIGRATOR, database.RUNTIME):
            for username in (role, role + '.project_ref-123'):
                with self.subTest(role=role, username=username):
                    parsed = database.database_url(url_for(role, username=username), role)
                    self.assertEqual(parsed.username, username)

    def test_driver_administrative_user_missing_fields_and_invalid_urls_are_rejected(self):
        cases = [
            '', 'no-es-una-url', None,
            URL.create('sqlite', database='archivo.db'),
            url_for(database.MIGRATOR).set(drivername='postgresql'),
            url_for(database.MIGRATOR).set(drivername='postgresql+psycopg2'),
            url_for(database.MIGRATOR, username='postgres'),
            url_for(database.MIGRATOR, username=database.RUNTIME),
            url_for(database.MIGRATOR, username='app_migrator.proyecto.extra'),
            URL.create('postgresql+psycopg', username=database.MIGRATOR,
                       password=PASSWORD, database='postgres'),
            URL.create('postgresql+psycopg', username=database.MIGRATOR,
                       password=PASSWORD, host='localhost'),
            URL.create('postgresql+psycopg', username=database.MIGRATOR,
                       host='localhost', database='postgres'),
        ]
        for value in cases:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(database.DatabaseConfigurationError) as raised:
                    database.database_url(value, database.MIGRATOR)
                self.assertNotIn(PASSWORD, str(raised.exception))

    def test_unknown_role_is_rejected_before_creating_an_engine(self):
        with patch.object(database, 'create_engine') as create:
            with self.assertRaises(database.DatabaseConfigurationError):
                database.database_url(url_for(database.RUNTIME), 'postgres')
        create.assert_not_called()

    def test_migration_engine_never_falls_back_to_runtime_url(self):
        with patch.dict(os.environ, {'DATABASE_URL': url_for(database.RUNTIME).render_as_string(hide_password=False)}, clear=True):
            with self.assertRaises(database.DatabaseConfigurationError):
                database.create_migration_engine()

    def test_runtime_engine_never_falls_back_to_migration_url(self):
        with patch.dict(os.environ, {'MIGRATION_DATABASE_URL': url_for(database.MIGRATOR).render_as_string(hide_password=False)}, clear=True):
            with self.assertRaises(database.DatabaseConfigurationError):
                database.create_runtime_engine()

    def test_engine_factories_keep_credentials_and_pools_separate(self):
        # Crear un Engine no abre una conexión: no se llama a connect().
        migrator = database.create_migration_engine(url_for(database.MIGRATOR))
        runtime = database.create_runtime_engine(url_for(database.RUNTIME))
        try:
            self.assertIsInstance(migrator.pool, NullPool)
            self.assertIsNot(migrator.pool, runtime.pool)
            self.assertEqual(migrator.url.username, database.MIGRATOR)
            self.assertEqual(runtime.url.username, database.RUNTIME)
            self.assertTrue(migrator.hide_parameters)
            self.assertTrue(runtime.hide_parameters)
        finally:
            migrator.dispose()
            runtime.dispose()


class EffectiveRoleTests(unittest.TestCase):
    def test_correct_identity_and_effective_permissions_are_accepted_for_each_role(self):
        for role in (database.MIGRATOR, database.RUNTIME):
            with self.subTest(role=role):
                connection = connection_for(role)
                self.assertEqual(database.validate_connection(connection, role), metadata_for(role))

    def test_changed_identity_schema_or_administrative_permissions_are_rejected(self):
        changes = (
            {'session_user': 'postgres'}, {'current_user': 'postgres'},
            {'database': 'otra_base'}, {'schema': 'auth'}, {'login': False},
            {'superuser': True}, {'createdb': True}, {'createrole': True},
            {'replication': True}, {'bypassrls': True}, {'connect': False},
            {'create_schema': True}, {'usage_public': False}, {'memberships': 1},
        )
        for role in (database.MIGRATOR, database.RUNTIME):
            for change in changes:
                with self.subTest(role=role, field=next(iter(change))):
                    connection = connection_for(role, **change)
                    with self.assertRaises(database.DatabaseAccessError) as raised:
                        database.validate_connection(connection, role)
                    self.assertIn(next(iter(change)), str(raised.exception))
                    self.assertNotIn(PASSWORD, str(raised.exception))

    def test_effective_create_public_permission_is_different_for_each_role(self):
        for role in (database.MIGRATOR, database.RUNTIME):
            connection = connection_for(role, create_public=role != database.MIGRATOR)
            with self.subTest(role=role):
                with self.assertRaisesRegex(database.DatabaseAccessError, 'create_public'):
                    database.validate_connection(connection, role)

    def test_dialect_default_schema_must_agree_with_public(self):
        connection = connection_for(database.MIGRATOR)
        connection.dialect.default_schema_name = 'auth'
        with self.assertRaisesRegex(database.DatabaseAccessError, 'default_schema_name'):
            database.validate_connection(connection, database.MIGRATOR)

    def test_unknown_role_does_not_execute_metadata_query(self):
        connection = connection_for(database.RUNTIME)
        with self.assertRaises(database.DatabaseConfigurationError):
            database.validate_connection(connection, 'postgres')
        connection.execute.assert_not_called()


class FirstModelTests(unittest.TestCase):
    def test_espacio_is_in_public_with_required_uuid_primary_key_and_name(self):
        table = Espacio.__table__
        self.assertEqual(table.schema, 'public')
        self.assertTrue(table.c.id.primary_key)
        self.assertFalse(table.c.id.nullable)
        self.assertIsInstance(table.c.id.type, Uuid)
        self.assertTrue(table.c.id.type.as_uuid)
        self.assertIsInstance(table.c.nombre.type, Text)
        self.assertFalse(table.c.nombre.nullable)

    def test_uuid_is_generated_in_python_without_a_server_function(self):
        column = Espacio.__table__.c.id
        self.assertIsNone(column.server_default)
        self.assertIsInstance(column.default.arg(None), UUID)


if __name__ == '__main__':
    unittest.main()
