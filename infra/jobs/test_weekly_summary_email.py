from datetime import UTC, datetime
from unittest import TestCase
from unittest.mock import MagicMock
from uuid import uuid4

from psycopg.pq import TransactionStatus

from deliver_reminder_email import DeliveryOutcome
from weekly_summary_email import render_weekly_summary, send_weekly_summary


class WeeklySummaryTests(TestCase):
    def setUp(self):
        self.scope = (uuid4(), uuid4())
        self.report = {
            'desde': '2026-02-09', 'hasta': '2026-02-15', 'proximos_desde': '2026-02-16',
            'gastos': [{'moneda': 'ARS', 'total': '100.00'}, {'moneda': 'USD', 'total': '10.00'}],
            'gastos_fijados': ['2.00', '200.00'], 'tasa': '100.00',
            'limite': {'moneda': 'ARS', 'importe': '1000.00'},
            'cantidad_proximos': 2, 'proximos': [{
                'vencimiento': '2026-02-19', 'nombre': 'Cuota de prueba', 'moneda': 'ARS',
                'saldo': '50.00', 'estimado': True,
            }],
        }

    def test_renders_two_currencies_budget_and_upcoming_balance(self):
        mail = render_weekly_summary(self.report, self.scope, 'https://piggo.example')
        self.assertIn('09/02 al 15/02', mail.texto)
        self.assertIn('Exceso: ARS 100,00', mail.texto)
        self.assertIn('Cuota de prueba · Estimado ARS 50,00', mail.texto)
        self.assertIn('Hay un vencimiento más', mail.texto)
        self.report['tasa'] = None
        self.assertIn('Conversión pendiente', render_weekly_summary(
            self.report, self.scope, 'https://piggo.example',
        ).texto)

    def test_sends_only_after_reserving_and_records_the_outcome(self):
        connection = MagicMock(autocommit=True)
        connection.info.transaction_status = TransactionStatus.IDLE
        connection.execute.return_value.fetchone.side_effect = [(self.report,), (True,), (True,),
                                                              (self.report,), (False,)]
        sender = MagicMock()
        sender.send.return_value = DeliveryOutcome('aceptada', 'sample')
        instant = datetime(2026, 2, 16, 12, tzinfo=UTC)
        args = (connection, instant, self.scope, 'user@example.com', 'https://piggo.example', sender)
        self.assertEqual(send_weekly_summary(*args).estado, 'aceptada')
        self.assertIsNone(send_weekly_summary(*args))
        sender.send.assert_called_once()
        attempt = sender.send.call_args.args[0]
        self.assertEqual(connection.execute.call_args_list[2].args[1], (attempt, 'aceptada'))
