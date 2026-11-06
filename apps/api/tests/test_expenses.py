import unittest
from decimal import Decimal
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.expenses import ExpenseInput, router

class ExpenseTests(unittest.TestCase):
    def payload(self, **changes):
        return dict(id=str(uuid4()),fecha='2026-11-06',descripcion='Comida',moneda='ARS',importe='0.10') | changes
    def test_exact_amounts(self):
        for value in ['0.10','1','999999999999.99']:
            self.assertEqual(ExpenseInput(**self.payload(importe=value)).importe, Decimal(value))
    def test_rejects_rounding_and_invalid_amounts(self):
        for value in [0.1,1,None,'0','-1','1.001','1e2','NaN','Infinity','1000000000000','1,25']:
            with self.subTest(value=value),self.assertRaises(ValidationError):
                ExpenseInput(**self.payload(importe=value))
    def test_invalid_dates_currency_and_identity(self):
        for changes in [dict(fecha='2026-02-30'),dict(fecha='06/11/2026'),dict(moneda='XXX'),dict(usuario_id=str(uuid4())),dict(descripcion='a\nb'),dict(descripcion=' '),dict(id='00000000-0000-0000-0000-000000000000')]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError): ExpenseInput(**self.payload(**changes))
    def test_auth_required(self):
        app=FastAPI();app.include_router(router);client=TestClient(app)
        path=f'/spaces/{uuid4()}/accounts/{uuid4()}/expenses'
        self.assertEqual(client.get(path).status_code,401)
        self.assertEqual(client.post(path,json=self.payload()).status_code,401)
