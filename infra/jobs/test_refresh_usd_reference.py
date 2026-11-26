import unittest

from refresh_usd_reference import normalize


class MarketRates(unittest.TestCase):
    def test_keeps_newest_valid_price_and_skips_invalid_markets(self):
        rows = [
            {'casa': 'blue', 'moneda': 'USD', 'venta': '1800.20', 'fechaActualizacion': '2024-01-02T10:00:00Z'},
            {'casa': 'blue', 'moneda': 'USD', 'venta': '1750.00', 'fechaActualizacion': '2024-01-01T10:00:00Z'},
            {'casa': 'oficial', 'moneda': 'USD', 'venta': 0, 'fechaActualizacion': '2024-01-01T10:00:00Z'},
        ]
        self.assertEqual(normalize(rows), [
            {'tipo': 'blue', 'tasa': '1800.2000', 'actualizada_en': '2024-01-02T10:00:00+00:00'},
        ])
        with self.assertRaises(ValueError):
            normalize(rows[2:])
