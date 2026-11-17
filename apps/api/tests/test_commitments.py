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
                        dict(total_cuotas=0),dict(total_cuotas=601),dict(total_cuotas=1.5),
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


class MonthlyCommitmentTests(unittest.TestCase):
    def test_invalid_month_is_rejected_before_query(self):
        from app.commitments import monthly_installments
        from fastapi import HTTPException
        for month in ('0000-01','2026-00','2026-13','2026-1','26-01','2026-01-01'):
            with self.subTest(month=month),self.assertRaises(HTTPException) as failure:
                monthly_installments(None,None,None,month)
            self.assertEqual(failure.exception.status_code,422)

    def test_calendar_extremes_and_empty_pages(self):
        from unittest.mock import Mock,patch
        from app.commitments import monthly_installments
        session=Mock()
        session.execute.return_value.mappings.return_value.all.return_value=[{'id':None,'totales':[]}]
        with patch('app.commitments.require_member'):
            for month,last in [('0001-01',date(1,1,31)),('2024-02',date(2024,2,29)),('9999-12',date(9999,12,31))]:
                result=monthly_installments(session,uuid4(),uuid4(),month,100)
                self.assertEqual(result,dict(mes=month,totales=[],items=[],next_offset=None))
                self.assertEqual(session.execute.call_args.args[1]['last'],last)

    def test_monthly_and_detail_routes_require_identity(self):
        app=FastAPI();app.include_router(router);client=TestClient(app);path=f'/spaces/{uuid4()}'
        self.assertEqual(client.get(path+'/installments?month=2026-11').status_code,401)
        self.assertEqual(client.get(path+f'/commitments/{uuid4()}').status_code,401)
        self.assertEqual(client.get(path+'/installments?month=2026-13').status_code,422)


class RecurringCommitmentTests(unittest.TestCase):
    def test_indefinite_count_and_pause_validation(self):
        from app.commitments import CommitmentPause
        values=CommitmentTests().payload(total_cuotas=None)
        self.assertIsNone(CommitmentInput(**values).total_cuotas)
        self.assertTrue(CommitmentPause(pausado=True,version=1).pausado)
        for bad in ({'pausado':'true','version':1},{'pausado':False,'version':True},
                    {'pausado':False,'version':0},{'pausado':True,'version':1,'importe':'1'}):
            with self.subTest(bad=bad),self.assertRaises(ValidationError):CommitmentPause(**bad)

    def test_indefinite_totals_are_only_generated_installments(self):
        from app.commitments import public_commitment
        row=dict(variable=False,id=uuid4(),espacio_id=uuid4(),cuenta_id=uuid4(),nombre='Servicio',moneda='ARS',
            importe=Decimal('100'),categoria=None,primer_vencimiento=date(2026,11,30),total_cuotas=None,
            cuotas_pagadas=1,pagado=Decimal('130'),total_generado=Decimal('200'),
            proximo_vencimiento=date(2026,12,30),pausado=False,version=2)
        result=public_commitment(row)
        self.assertEqual((result['total'],result['pagado'],result['pendiente']),('200.00','130.00','70.00'))
        self.assertIsNone(result['total_cuotas'])


class VariableCommitmentTests(unittest.TestCase):
    def test_variable_is_strict_and_only_indefinite(self):
        values=CommitmentTests().payload(total_cuotas=None,variable=True)
        self.assertTrue(CommitmentInput(**values).variable)
        for changes in ({'variable':'true'},{'total_cuotas':10}):
            with self.assertRaises(ValidationError):CommitmentInput(**(values|changes))

    def test_batch_validation(self):
        from app.commitments import ConfirmationsInput
        item=dict(id=str(uuid4()),importe='100.10',version=1)
        self.assertEqual(ConfirmationsInput(items=[item]).items[0].importe,Decimal('100.10'))
        for items in ([],[item,item],[item]*101,[item|{'importe':100}],[item|{'version':True}],[item|{'moneda':'USD'}]):
            with self.assertRaises(ValidationError):ConfirmationsInput(items=items)

    def test_draft_is_distinct_from_pending(self):
        row=CommitmentTests().row()
        row.update(estimado=True,version=1)
        result=public_installment(row,date(2026,11,17))
        self.assertEqual((result['estado'],result['estimado'],result['version']),('borrador',True,1))

    def test_draft_routes_require_identity(self):
        app=FastAPI();app.include_router(router);client=TestClient(app);path=f'/spaces/{uuid4()}'
        self.assertEqual(client.get(path+'/installment-drafts').status_code,401)
        body={'items':[{'id':str(uuid4()),'importe':'100','version':1}]}
        self.assertEqual(client.post(path+'/installment-confirmations',json=body).status_code,401)
