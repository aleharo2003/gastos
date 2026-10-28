import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from app.db.unit_of_work import InvalidDatabaseContext, _uuid, runtime_transaction


class ContextValidationTests(unittest.TestCase):
    def test_uuid_object_is_serialized(self):
        value = uuid4()
        self.assertEqual(_uuid(value, 'usuario_id'), str(value))

    def test_uuid_string_is_normalized(self):
        value = uuid4()
        self.assertEqual(_uuid(value.hex.upper(), 'usuario_id'), str(value))

    def test_invalid_user_is_rejected_before_opening_session(self):
        for value in (None, '', 'no-es-uuid', 12, True, []):
            with self.subTest(value=value), patch('app.db.unit_of_work.Session') as factory:
                with self.assertRaises(InvalidDatabaseContext):
                    with runtime_transaction(None, usuario_id=value):
                        self.fail('No debe abrir el bloque')
                factory.assert_not_called()

    def test_invalid_workspace_is_rejected_before_opening_session(self):
        for value in ('', 'no-es-uuid', 12, True, []):
            with self.subTest(value=value), patch('app.db.unit_of_work.Session') as factory:
                with self.assertRaises(InvalidDatabaseContext):
                    with runtime_transaction(None, usuario_id=uuid4(), espacio_id=value):
                        self.fail('No debe abrir el bloque')
                factory.assert_not_called()

    def test_error_does_not_echo_untrusted_value(self):
        with self.assertRaises(InvalidDatabaseContext) as caught:
            _uuid('dato-privado', 'usuario_id')
        self.assertNotIn('dato-privado', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
