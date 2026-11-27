from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from process_daily import main, run_tasks


class DailyProcessTests(TestCase):
    def test_continues_after_a_failure_and_keeps_the_result_without_secrets(self):
        failed = Mock(side_effect=RuntimeError('private-dsn'))
        remaining = Mock(return_value=7)
        output = StringIO()
        with TemporaryDirectory() as tmp, redirect_stdout(output):
            path = Path(tmp, 'summary.md')
            self.assertEqual(run_tasks([('Cuotas', failed), ('Vencimientos', remaining)], path), 1)
            summary = path.read_text(encoding='utf-8')
        failed.assert_called_once_with()
        remaining.assert_called_once_with()
        self.assertIn('Cuotas: Falló', summary)
        self.assertIn('Vencimientos: OK (7)', summary)
        self.assertNotIn('private-dsn', output.getvalue() + summary)

    def test_manual_quotes_only_does_not_run_database_maintenance(self):
        with patch('sys.argv', ['process_daily.py', 'cotizaciones']), patch('process_daily.generate') as generate, \
                patch('process_daily.mark_overdue') as mark, patch('process_daily.refresh', return_value=3) as refresh, \
                patch.dict('os.environ', {'GITHUB_STEP_SUMMARY': ''}), redirect_stdout(StringIO()):
            self.assertEqual(main(), 0)
        generate.assert_not_called()
        mark.assert_not_called()
        refresh.assert_called_once_with()
