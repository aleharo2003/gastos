import json
import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

from deliver_reminder_email import DeliveryOutcome
from deliver_test_reminder import deliver_test_reminder
from verified_reminder_recipient import verified_reminder_recipient


class VerifiedRecipientTests(unittest.TestCase):
    def setUp(self):
        self.user, self.space = uuid4(), uuid4()
        self.project = 'a' * 20
        self.key = 'sb_publishable_ficticia'
        self.token = 'token-de-prueba'
        self.address = 'usuario@example.test'
        self.account = {
            'id': str(self.user), 'email': self.address,
            'email_confirmed_at': '2026-11-18T14:20:00Z',
        }

    def check(self):
        return verified_reminder_recipient(self.project, self.key, self.token, self.user, self.address)

    def test_confirms_address_with_user_session(self):
        with patch('verified_reminder_recipient.HTTPSConnection') as connect:
            https = connect.return_value
            response = https.getresponse.return_value
            response.status = 200
            response.read.return_value = json.dumps(self.account).encode()
            self.assertEqual(self.check(), self.address)
            connect.assert_called_once_with(self.project + '.supabase.co', timeout=10)
            https.request.assert_called_once_with('GET', '/auth/v1/user', headers={
                'Accept': 'application/json', 'apikey': self.key, 'Authorization': 'Bearer ' + self.token,
            })
            https.close.assert_called_once()

    def test_rejects_expired_token_and_different_confirmed_account(self):
        for status, account in (
            (401, self.account), (302, self.account), (200, self.account | {'id': str(uuid4())}),
            (200, self.account | {'email': 'otra-cuenta@example.test'}),
        ):
            with self.subTest(status=status), patch('verified_reminder_recipient.HTTPSConnection') as connect:
                response = connect.return_value.getresponse.return_value
                response.status = status
                response.read.return_value = json.dumps(account).encode()
                with self.assertRaises(RuntimeError):
                    self.check()

    def test_does_not_deliver_without_confirmation(self):
        for change in (
            {'email_confirmed_at': None}, {'email_confirmed_at': 'ayer'}, {'is_anonymous': True},
        ):
            with self.subTest(change=change), patch('verified_reminder_recipient.HTTPSConnection') as connect:
                response = connect.return_value.getresponse.return_value
                response.status = 200
                response.read.return_value = json.dumps(self.account | change).encode()
                with patch('deliver_test_reminder.deliver_reminder_email') as deliver:
                    self.assertIsNone(self.pilot())
                    deliver.assert_not_called()

    def test_pilot_passes_only_the_verified_destination(self):
        connection, sender = MagicMock(), MagicMock()
        instant = datetime(2026, 11, 18, 18, tzinfo=UTC)
        with patch('deliver_test_reminder.verified_reminder_recipient', return_value=self.address) as lookup, \
             patch('deliver_test_reminder.deliver_reminder_email', return_value=DeliveryOutcome('aceptada', 'mail-id')) as deliver:
            result = self.pilot(connection, instant, sender)
            lookup.assert_called_once_with(self.project, self.key, self.token, self.user, self.address)
            deliver.assert_called_once_with(
                connection, instant, (self.user, self.space), self.address, 'https://piggo.example.test/', sender, None,
            )
        self.assertEqual(result, DeliveryOutcome('aceptada', 'mail-id'))

    def test_rejects_secret_key_before_connecting(self):
        with patch('verified_reminder_recipient.HTTPSConnection') as connect, self.assertRaises(ValueError):
            verified_reminder_recipient(self.project, 'sb_secret_ficticia', self.token, self.user, self.address)
        connect.assert_not_called()

    def pilot(self, connection=None, instant=None, sender=None):
        return deliver_test_reminder(
            connection, instant, (self.user, self.space), project_ref=self.project, public_key=self.key,
            access_token=self.token, expected_email=self.address, app_url='https://piggo.example.test/', sender=sender,
        )
