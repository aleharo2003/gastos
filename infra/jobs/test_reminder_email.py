import unittest
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from reminder_email import prepare_reminder_emails


class ReminderEmailTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.user, self.space, self.other_space = uuid4(), uuid4(), uuid4()
        self.instant = datetime(2026, 11, 18, 12, tzinfo=UTC)
        self.url = 'https://piggo.example.test/'

    def row(self, **overrides):
        return {
            'usuario_id': self.user, 'espacio_id': self.space, 'fecha_aviso': date(2026, 11, 18),
            'vencimiento': date(2026, 11, 19), 'evento': 'vencimiento', 'nombre': 'Terreno',
            'numero': 4, 'moneda': 'USD', 'pendiente': Decimal('70.25'),
            'estimado': False, 'pendiente_ajuste': True,
        } | overrides

    def test_groups_by_user_and_space_and_includes_currency_source(self):
        self.cursor.fetchall.return_value = [
            self.row(),
            self.row(nombre='Luz', moneda='ARS', pendiente=Decimal('1500.50'),
                     estimado=True, pendiente_ajuste=False, evento='vencida'),
            self.row(espacio_id=self.other_space, nombre='Otro espacio'),
            self.row(usuario_id=uuid4(), nombre='Otro usuario'),
        ]
        first, other_space, other_user = prepare_reminder_emails(
            self.connection, self.instant, self.url, {self.space: Decimal('1000')},
        )
        self.assertEqual((first.usuario_id, first.espacio_id), (self.user, self.space))
        self.assertIn('18/11/2026', first.asunto)
        self.assertIn('USD 70,25 (pendiente de ajuste)', first.texto)
        self.assertIn('Estimado en ARS: 70.250,00 (1 USD = ARS 1000)', first.texto)
        self.assertIn('ARS 1.500,50 (importe estimado)', first.texto)
        self.assertIn(self.url, first.texto)
        self.assertNotIn('Otro espacio', first.texto)
        self.assertNotIn('Otro usuario', first.texto)
        self.assertIn('Sin cotización de referencia', other_space.texto)
        self.assertIn('Otro usuario', other_user.texto)
        self.assertEqual(self.cursor.execute.call_args.args[1], (self.instant,))

    def test_returns_no_message_when_there_are_no_pending_reminders(self):
        self.cursor.fetchall.return_value = []
        self.assertEqual(prepare_reminder_emails(self.connection, self.instant, self.url), ())

    def test_requires_aware_instant_and_safe_app_link(self):
        for instant, url in (
            (self.instant.replace(tzinfo=None), self.url),
            (self.instant, 'http://piggo.example.test/'),
            (self.instant, 'https://user@piggo.example.test/'),
            (self.instant, 'https://piggo.example.test/\nOtra línea'),
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                prepare_reminder_emails(self.connection, instant, url)
        self.connection.cursor.assert_not_called()
