from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest import TestCase
from unittest.mock import patch

from deliver_reminder_email import DeliveryOutcome
from notify_daily_failure import main


class DailyFailureNoticeTests(TestCase):
    def test_without_a_recipient_uses_only_the_actions_result(self):
        with patch.dict('os.environ', {}, clear=True), patch('notify_daily_failure.ResendSender') as sender, \
                redirect_stdout(StringIO()):
            self.assertEqual(main(), 0)
        sender.assert_not_called()

    def test_retries_use_the_same_delivery_key(self):
        env = {
            'PIGGO_DAILY_ALERT_EMAIL': 'operator@example.com', 'RESEND_API_KEY': 'private-key',
            'PIGGO_DAILY_FROM_EMAIL': 'piggo@example.com', 'GITHUB_SERVER_URL': 'https://github.com',
            'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_RUN_ID': '42',
        }
        output = StringIO()
        with patch.dict('os.environ', env, clear=True), patch('notify_daily_failure.ResendSender') as sender, \
                redirect_stdout(output), redirect_stderr(output):
            send = sender.return_value.send
            send.side_effect = [RuntimeError('private-key'), DeliveryOutcome('aceptada')]
            self.assertEqual(main(), 1)
            self.assertEqual(main(), 0)
        first, second = (call.args for call in send.call_args_list)
        self.assertEqual(first[0], second[0])
        self.assertEqual(second[1], 'operator@example.com')
        self.assertIn('https://github.com/owner/repo/actions/runs/42', second[2].texto)
        self.assertNotIn('private-key', output.getvalue())
