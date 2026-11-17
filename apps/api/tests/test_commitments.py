import unittest
from datetime import date
from decimal import Decimal
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.commitments import CommitmentInput,PaymentInput,monthly_due,public_installment,router


class CommitmentTests(unittest.TestCase):
    def payload(self,**changes):
        return dict(id=str(uuid4()),cuenta_id=str(uuid4()),nombre='Pagares',moneda='USD',importe='250.00',
                    categoria='vivienda',primer_vencimiento='2026-11-30',total_cuotas=10)|changes

    def test_monthly_calendar_keeps_anchor_and_handles_leap_year(self):
        self.assertEqual([monthly_due(date(2024,1,31),n) for n in range(3)],
                         [date(2024,1,31),date(2024,2,29),date(2024,3,31)])
        self.assertEqual(monthly_due(date(2025,1,31),1),date(2025,2,28))
        self.assertEqual(monthly_due(date(2026,12,15),1),date(2027,1,15))

    def test_money_count_and_date_validation(self):
        self.assertEqual(CommitmentInput(**self.payload()).importe,Decimal('250.00'))
        for changes in [dict(importe=250),dict(importe='0'),dict(importe='1.001'),dict(total_cuotas=True),
                        dict(total_cuotas=0),dict(total_cuotas=601),dict(total_cuotas=None),
                        dict(primer_vencimiento='2026-02-30'),dict(primer_vencimiento='9999-12-31',total_cuotas=2),
                        dict(usuario_id=str(uuid4())),dict(categoria='inventada')]:
            with self.subTest(changes=changes),self.assertRaises(ValidationError):CommitmentInput(**self.payload(**changes))

    def test_payment_money_and_currency_are_not_client_controlled(self):
        good=dict(id=str(uuid4()),cuenta_id=str(uuid4()),fecha='2026-11-17',importe='0.10')
        self.assertEqual(PaymentInput(**good).importe,Decimal('0.10'))
        for changes in [dict(importe=0.1),dict(importe='-1'),dict(moneda='ARS'),dict(cuota_id=str(uuid4()))]:
            with self.subTest(changes=changes),self.assertRaises(ValidationError):PaymentInput(**(good|changes))

    def row(self,paid='0',due=date(2026,11,17)):
        return dict(id=uuid4(),espacio_id=uuid4(),compromiso_id=uuid4(),numero=1,vencimiento=due,importe=Decimal('100'),pagado=Decimal(paid))

    def test_partial_paid_and_overdue_use_local_day(self):
        today=date(2026,11,17)
        self.assertFalse(public_installment(self.row(),today)['vencida'])
        partial=public_installment(self.row('30',date(2026,11,16)),today)
        self.assertEqual((partial['estado'],partial['pendiente'],partial['vencida']),('parcial','70.00',True))
        complete=public_installment(self.row('100',date(2026,11,16)),today)
        self.assertEqual((complete['estado'],complete['pendiente'],complete['vencida']),('pagada','0.00',False))

    def test_authentication(self):
        app=FastAPI();app.include_router(router);client=TestClient(app);path=f'/spaces/{uuid4()}'
        self.assertEqual(client.get(path+'/commitments').status_code,401)
        self.assertEqual(client.post(path+'/commitments',json=self.payload()).status_code,401)
        payment=dict(id=str(uuid4()),cuenta_id=str(uuid4()),fecha='2026-11-17',importe='10')
        self.assertEqual(client.post(path+f'/installments/{uuid4()}/payments',json=payment).status_code,401)
