import unittest
from datetime import date
from decimal import Decimal

from pydantic import ValidationError

from app.adjustment_indices import IndexValueInput


class AdjustmentIndexInputTests(unittest.TestCase):
    def test_accepts_exact_signed_percentages_and_explicit_month(self):
        value = IndexValueInput(indice=' CAC ', periodo='2024-02', variacion='-0.1234')
        self.assertEqual(value.indice, 'CAC')
        self.assertEqual(value.periodo, date(2024, 2, 1))
        self.assertEqual(value.variacion, Decimal('-0.1234'))

    def test_rejects_invalid_month_and_percentage(self):
        valid = {'indice': 'CAC', 'periodo': '2024-02', 'variacion': '2.5'}
        for changes in (
            {'periodo': '2024-02-01'}, {'periodo': '0000-02'}, {'periodo': '2024-13'},
            {'variacion': 2.5}, {'variacion': '2.12345'}, {'variacion': '-100'},
            {'variacion': 'NaN'}, {'indice': 'C\nAC'},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                IndexValueInput(**(valid | changes))
