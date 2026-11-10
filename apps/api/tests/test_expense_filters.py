import unittest
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.expenses import ExpenseInput, ExpenseFilters, router

class FilterValidation(unittest.TestCase):
    def test_category_contract(self):
        payload=dict(id=uuid4(),fecha='2026-11-10',descripcion='Cerveza',moneda='ARS',importe='2.50')
        self.assertIsNone(ExpenseInput(**payload).categoria)
        self.assertEqual(ExpenseInput(**payload,categoria='alimentos').categoria,'alimentos')
        for value in ['inventada','',2,{},'sin_categoria']:
            with self.subTest(value=value),self.assertRaises(ValidationError):
                ExpenseInput(**payload,categoria=value)

    def test_search_validation(self):
        self.assertEqual(ExpenseFilters(texto='  10%  ').texto,'10%')
        for value in ['x'*161,'linea\nsiguiente','\x7f']:
            with self.assertRaises(ValidationError): ExpenseFilters(texto=value)

    def test_bad_query_rejected_before_database(self):
        app=FastAPI();app.include_router(router);client=TestClient(app)
        path=f'/spaces/{uuid4()}/accounts/{uuid4()}/expenses'
        for query in [{'desde':'2026-02-30'},{'moneda':'XXX'},{'categoria':'invalida'},{'texto':'\n'},{'texto':'x'*161}]:
            with self.subTest(query=query):self.assertEqual(client.get(path,params=query).status_code,422)
