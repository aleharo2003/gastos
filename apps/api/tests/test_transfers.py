import unittest
from uuid import uuid4
from decimal import Decimal
from pydantic import ValidationError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.transfers import TransferInput,router


class TransferTests(unittest.TestCase):
    def payload(self,**changes):
        return dict(id=str(uuid4()),origen_id=str(uuid4()),destino_id=str(uuid4()),
                    fecha='2026-11-17',descripcion='Ahorro',moneda='ARS',importe='0.10')|changes

    def test_same_currency_and_exact_money(self):
        for currency in ['ARS','USD','EUR']:
            self.assertEqual(TransferInput(**self.payload(moneda=currency)).importe,Decimal('0.10'))

    def test_rejects_same_account_and_empty_identifiers(self):
        account=str(uuid4())
        for changes in [dict(origen_id=account,destino_id=account),
                        dict(origen_id='00000000-0000-0000-0000-000000000000'),
                        dict(destino_id='00000000-0000-0000-0000-000000000000')]:
            with self.subTest(changes=changes),self.assertRaises(ValidationError):
                TransferInput(**self.payload(**changes))

    def test_rejects_rounding_currency_exchange_and_forged_identity(self):
        for amount in [1,1.2,'0','-1','1.001','1e2','NaN','1000000000000']:
            with self.subTest(amount=amount),self.assertRaises(ValidationError):
                TransferInput(**self.payload(importe=amount))
        for changes in [dict(moneda='XXX'),dict(moneda_destino='USD'),
                        dict(usuario_id=str(uuid4())),dict(fecha='2026-02-30')]:
            with self.subTest(changes=changes),self.assertRaises(ValidationError):
                TransferInput(**self.payload(**changes))

    def test_requires_authentication(self):
        app=FastAPI();app.include_router(router);client=TestClient(app)
        path=f'/spaces/{uuid4()}/transfers'
        self.assertEqual(client.get(path).status_code,401)
        self.assertEqual(client.post(path,json=self.payload()).status_code,401)
