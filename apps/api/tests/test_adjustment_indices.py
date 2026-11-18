import unittest
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from pydantic import ValidationError

from app.adjustment_indices import IndexValueInput, parse_index_csv


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


class AdjustmentIndexCsvTests(unittest.TestCase):
    def test_parses_comma_and_spreadsheet_semicolon_csv(self):
        variants = (
            'indice,periodo,variacion\nCAC,2024-02,"-0,1234%"\n\n"Obra, norte",2024-03,2.3\n',
            '\ufeffindice;periodo;variacion\r\nCAC;2024-02;-0,1234 %\r\n\r\nObra, norte;2024-03;2,3\r\n',
        )
        for content in variants:
            with self.subTest(content=content):
                self.assertEqual(parse_index_csv(content), [
                    {'linea': 2, 'indice': 'CAC', 'periodo': '2024-02-01', 'variacion': '-0.1234'},
                    {'linea': 4, 'indice': 'Obra, norte', 'periodo': '2024-03-01', 'variacion': '2.3'},
                ])

    def test_reports_invalid_rows_instead_of_partial_success(self):
        header = 'indice,periodo,variacion\n'
        for content, detail in (
            ('CAC,2024-02,0', 'primera fila'),
            (header, 'al menos una'),
            (header + 'CAC,2024-13,0', 'Fila 2: valor inválido en periodo'),
            (header + 'CAC,2024-02,2,3', 'Fila 2: se esperaban tres columnas'),
            (header + 'CAC,2024-02,0\nCAC,2024-02,0', 'Fila 3: índice y período repetidos'),
            (header + 'CAC,2024-02,"2.3', 'CSV inválido'),
            (header + 'CAC,2024-02,0\n' * 5000, '32 KiB'),
            (header + ''.join(f'CAC,{year}-01,0\n' for year in range(1000, 1501)), '500 variaciones'),
        ):
            with self.subTest(detail=detail), self.assertRaises(HTTPException) as error:
                parse_index_csv(content)
            self.assertEqual(error.exception.status_code, 422)
            self.assertIn(detail, error.exception.detail)
