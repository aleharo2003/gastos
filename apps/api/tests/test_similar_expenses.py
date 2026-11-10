import unittest
from unittest.mock import patch
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.similar_expenses import similarity
from app.expenses import router, list_similar_expenses


class SimilarTests(unittest.TestCase):
    def test_same_description_case_and_accents(self):
        self.assertEqual(similarity('CAFÉ con leche','Café con leche'),1)

    def test_variants_and_word_order(self):
        for left,right in [('cerveza','serbesa'),('compra de cerveza','cerveza artesanal'),('cafe leche','leche y café'),('farmacia barrio','farmacia del barrio')]:
            with self.subTest(left=left,right=right):
                self.assertEqual(similarity(left,right),2)
                self.assertEqual(similarity(right,left),2)

    def test_does_not_match_only_generic_words_or_category(self):
        for left,right in [('Compra pan','Compra seguro'),('Seguro auto','Seguro casa'),('gas','gato'),('pago de','compra en'),('cerveza','supermercado cerveza pan vino'),('casa casas','casa segura')]:
            with self.subTest(left=left,right=right):self.assertEqual(similarity(left,right),0)

    def test_endpoint_requires_identity(self):
        app=FastAPI();app.include_router(router);client=TestClient(app)
        path=f'/spaces/{uuid4()}/accounts/{uuid4()}/expenses/{uuid4()}/similar'
        self.assertEqual(client.get(path).status_code,401)

    def test_cursor_closes_on_error(self):
        class Source:
            def scalar_one_or_none(self):return 'Cerveza'
        class Result:
            closed=False
            def mappings(self):return iter([{'descripcion':'Cerveza'}])
            def close(self):self.closed=True
        result=Result()
        class Session:
            calls=0
            def execute(self,*args,**kwargs):
                self.calls+=1
                return Source() if self.calls==1 else result
        with patch('app.expenses.require_account'),patch('app.expenses.similarity',side_effect=RuntimeError('test')):
            with self.assertRaises(RuntimeError):list_similar_expenses(Session(),None,None,None,uuid4())
        self.assertTrue(result.closed)
