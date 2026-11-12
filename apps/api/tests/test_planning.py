import unittest
from uuid import uuid4
from pydantic import ValidationError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.planning import PlanUpdate,Money,router,EMPTY

class PlanningTests(unittest.TestCase):
    def test_rejects_money_rounding_or_wrong_currency(self):
        for amount in ['0','-1','1e2','1.001',1.2,'NaN']:
            with self.subTest(amount=amount),self.assertRaises(ValidationError):Money(moneda='USD',importe=amount)
        with self.assertRaises(ValidationError):Money(moneda='EUR',importe='1.00')
        self.assertEqual(str(Money(moneda='ARS',importe='1').importe),'1.00')
    def test_rejects_duplicate_concepts_and_unknown_settings(self):
        row={'id':str(uuid4()),'concepto':'Verduras','frecuencia':'semana','moneda':'ARS','importe':'30000'}
        with self.assertRaises(ValidationError):PlanUpdate(version=0,datos=EMPTY|{'conceptos':[row,row]})
        with self.assertRaises(ValidationError):PlanUpdate(version=0,datos=EMPTY|{'cuenta_id':str(uuid4())})
        with self.assertRaises(ValidationError):PlanUpdate(version=True,datos=EMPTY)
        with self.assertRaises(ValidationError):PlanUpdate(version=0,datos=EMPTY|{'conceptos':[row|{'id':str(uuid4())} for _ in range(41)]})
    def test_auth_required(self):
        app=FastAPI();app.include_router(router);client=TestClient(app);path=f'/spaces/{uuid4()}/spending-plan'
        self.assertEqual(client.get(path).status_code,401)
        self.assertEqual(client.post(path,json={'version':0,'datos':EMPTY}).status_code,401)
