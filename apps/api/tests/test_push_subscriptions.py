import unittest

from pydantic import ValidationError

from app.push_subscriptions import PushSubscription


class PushSubscriptionTests(unittest.TestCase):
    def test_accepts_browser_push_provider_and_rejects_non_provider_urls(self):
        keys = {'p256dh': 'B' + 'A' * 86, 'auth': 'A' * 22}
        endpoint = 'https://fcm.googleapis.com/fcm/send/test'
        self.assertEqual(PushSubscription(endpoint=endpoint, keys=keys).endpoint, endpoint)
        for rejected in ('https://127.0.0.1/push', 'http://fcm.googleapis.com/push',
                         'https://fcm.googleapis.com@private.example/push',
                         'https://web.push.apple.com:8443/push', 'https://fcm.googleapis.com/push#fragment'):
            with self.subTest(rejected=rejected), self.assertRaises(ValidationError):
                PushSubscription(endpoint=rejected, keys=keys)
