import unittest
from unittest.mock import patch
from app.expense_search import ExpenseSearch
from app.expenses import ExpenseFilters, list_expenses


class SearchTests(unittest.TestCase):
    def test_requested_spelling_variants(self):
        for query in ['cervesa','cerbeza','serbesa','cerveaz','cervea']:
            with self.subTest(query=query):
                self.assertEqual(ExpenseSearch(query).match('Compra de cerveza artesanal'),2)
                self.assertEqual(ExpenseSearch(query,False).match('Compra de cerveza artesanal'),0)

    def test_accents_case_and_substrings(self):
        for query,description in [('CAFE','Café con leche'),('cafe','Cafe\u0301 con leche'),('cer','Cerveza'),('PAN','Panadería'),('10%_oferta','Cerveza 10%_oferta')]:
            with self.subTest(query=query):
                self.assertEqual(ExpenseSearch(query,False).match(description),1)

    def test_all_words_required(self):
        self.assertEqual(ExpenseSearch('serbesa pan').match('Pan y cerveza'),2)
        self.assertEqual(ExpenseSearch('serbesa pan').match('Cerveza sola'),0)
        self.assertEqual(ExpenseSearch('cerveza pan',False).match('Pan y cerveza'),0)

    def test_short_words_numbers_and_unrelated_terms(self):
        for query,description in [('gas','gato'),('luz','lujo'),('pan','paz'),('2026','2025'),('cerveza','Seguro del auto'),('10X_oferta','10%_oferta'),("%' OR true --",'Compra de cerveza'),('','Cerveza'),('\u0301','Cerveza')]:
            with self.subTest(query=query):self.assertEqual(ExpenseSearch(query).match(description),0)

    def test_correctly_written_query_also_finds_misspelled_description(self):
        self.assertEqual(ExpenseSearch('cerveza').match('Compra de serbesa'),2)

    def test_close_stream_on_match_error(self):
        class Result:
            closed=False
            def mappings(self):return iter([{'descripcion':'Cerveza'}])
            def close(self):self.closed=True
        result=Result()
        class Session:
            def execute(self,*args,**kwargs):return result
        with patch('app.expenses.require_account'),patch('app.expenses.ExpenseSearch.match',side_effect=RuntimeError('test')):
            with self.assertRaises(RuntimeError):
                list_expenses(Session(),None,None,None,filters=ExpenseFilters(texto='cerveza'))
        self.assertTrue(result.closed)
