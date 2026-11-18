import json
import unittest
from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

from psycopg.pq import TransactionStatus

from deliver_reminder_email import DeliveryOutcome, ResendSender, deliver_reminder_email
from reminder_email import ReminderEmail


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.instant = datetime(2026, 11, 18, 12, tzinfo=UTC)
        self.attempt = uuid4()
        self.scope = uuid4(), uuid4()
        self.message = ReminderEmail(*self.scope, date(2026, 11, 18), 'Recordatorio', 'Cuota pendiente')
        self.sender = ResendSender('clave-ficticia', 'piggo@example.test')
        self.recipient = 'usuario@example.test'
        self.app_url = 'https://piggo.example.test/'

    def test_provider_request_uses_attempt_as_idempotency_key(self):
        with patch('deliver_reminder_email.HTTPSConnection') as connect:
            https = connect.return_value
            response = https.getresponse.return_value
            response.status = 200
            response.read.return_value = b'{"id":"respuesta-resend"}'

            result = self.sender.send(self.attempt, self.recipient, self.message)

        self.assertEqual(result, DeliveryOutcome('aceptada', 'respuesta-resend'))
        connect.assert_called_once_with('api.resend.com', timeout=10)
        args, options = https.request.call_args
        self.assertEqual(args, ('POST', '/emails'))
        self.assertEqual(options['headers']['Idempotency-Key'], str(self.attempt))
        self.assertEqual(json.loads(options['body']), {
            'from': 'piggo@example.test', 'to': [self.recipient],
            'subject': self.message.asunto, 'text': self.message.texto,
        })
        https.close.assert_called_once()

    def test_only_confirmed_rate_limit_is_retriable(self):
        for status, raw, expected in (
            (429, b'{"name":"rate_limit_exceeded"}', 'reintento'),
            (429, b'{"name":"daily_quota_exceeded"}', 'incierta'),
            (500, b'{"name":"application_error"}', 'incierta'),
            (200, b'{"id":""}', 'incierta'),
            (200, b'x' * 4097, 'incierta'),
        ):
            with self.subTest(status=status, expected=expected), patch('deliver_reminder_email.HTTPSConnection') as connect:
                response = connect.return_value.getresponse.return_value
                response.status = status
                response.read.return_value = raw
                self.assertEqual(self.sender.send(self.attempt, self.recipient, self.message), DeliveryOutcome(expected))

        with patch('deliver_reminder_email.HTTPSConnection') as connect:
            connect.return_value.getresponse.side_effect = TimeoutError
            self.assertEqual(self.sender.send(self.attempt, self.recipient, self.message), DeliveryOutcome('incierta'))

    def connection(self):
        connection = MagicMock()
        connection.autocommit = True
        connection.info.transaction_status = TransactionStatus.IDLE
        return connection

    def test_commits_before_provider_and_records_its_result(self):
        connection = self.connection()
        reservation, resolution = MagicMock(), MagicMock()
        reservation.fetchone.return_value = (self.attempt,)
        resolution.fetchone.return_value = (True,)
        connection.execute.side_effect = [reservation, resolution]
        outcome = DeliveryOutcome('aceptada', 'referencia')

        def accepted(*args):
            connection.transaction.return_value.__exit__.assert_called_once()
            self.assertEqual(args, (self.attempt, self.recipient, self.message))
            return outcome

        sender = MagicMock()
        sender.send.side_effect = accepted
        with patch('deliver_reminder_email.prepare_reminder_emails', return_value=(self.message,)) as prepare:
            result = deliver_reminder_email(connection, self.instant, self.scope, self.recipient, self.app_url, sender)
        self.assertEqual(result, outcome)
        prepare.assert_called_once_with(connection, self.instant, self.app_url, None, scope=self.scope)
        self.assertEqual(connection.execute.call_args.args[1], (self.attempt, 'aceptada', 'referencia'))

    def test_no_reservation_means_no_provider_call(self):
        connection = self.connection()
        connection.execute.return_value.fetchone.return_value = (None,)
        sender = MagicMock()
        self.assertIsNone(deliver_reminder_email(connection, self.instant, self.scope, self.recipient, self.app_url, sender))
        sender.send.assert_not_called()

    def test_does_not_send_inside_an_existing_transaction(self):
        connection = self.connection()
        connection.info.transaction_status = TransactionStatus.INTRANS
        with self.assertRaises(ValueError):
            deliver_reminder_email(connection, self.instant, self.scope, self.recipient, self.app_url, MagicMock())
        connection.execute.assert_not_called()
