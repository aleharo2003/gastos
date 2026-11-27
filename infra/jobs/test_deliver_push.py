from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from pywebpush import WebPushException
from requests import Response

from deliver_push import PAYLOAD, RESERVE, RESOLVE, PushHttpSession, deliver, send_push


class DeliverPushTests(TestCase):
    def test_classifies_provider_responses_without_retrying_uncertain_deliveries(self):
        for code, expected in [(201, 'aceptado'), (404, 'vencido'), (410, 'vencido'),
                               (429, 'reintento'), (500, 'incierto')]:
            with self.subTest(code=code):
                response = Response()
                response.status_code = code
                provider = MagicMock(return_value=response)
                if code >= 400:
                    provider.side_effect = WebPushException('provider', response=response)
                status = send_push(None, 'https://fcm.googleapis.com/send/a', 'key', 'auth',
                                   'private', 'mailto:user@example.com', provider)
                self.assertEqual(status, expected)
                self.assertEqual(provider.call_args.kwargs['data'], PAYLOAD)

    def test_delivery_resolves_the_reserved_attempt(self):
        connection = MagicMock(autocommit=True)
        cursor = connection.cursor.return_value.__enter__.return_value
        attempt = uuid4()
        cursor.fetchone.side_effect = [
            ('app_jobs','app_jobs',False,False,False,False,False,False,0),
            (attempt, 'https://fcm.googleapis.com/send/a', 'key', 'auth'), (True,), None,
        ]
        expired = MagicMock(return_value=MagicMock(status_code=410))
        stats = deliver(connection, None, 'private', 'mailto:user@example.com', send=expired)
        self.assertEqual(stats['vencido'], 1)
        self.assertEqual(cursor.execute.call_args_list[-2].args,
                         (RESOLVE, (attempt, 'vencido', 'https://fcm.googleapis.com/send/a', 'key', 'auth')))
        self.assertEqual(cursor.execute.call_args_list[-1].args, (RESERVE,))

    def test_outbound_request_uses_only_provider_hosts_and_never_follows_redirects(self):
        with PushHttpSession() as http, patch('requests.Session.request') as request:
            with self.assertRaises(ValueError):
                http.post('https://private.example/push')
            request.assert_not_called()
            http.post('https://fcm.googleapis.com/fcm/send/test')
            self.assertFalse(request.call_args.kwargs['allow_redirects'])
