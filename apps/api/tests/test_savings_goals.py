import unittest
from datetime import date
from decimal import Decimal
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.savings_goals import GoalInput,GoalEdit,public_goal,router


class GoalTests(unittest.TestCase):
    def payload(self,**changes):
        return dict(id=str(uuid4()),cuenta_id=str(uuid4()),nombre='Vacaciones',moneda='ARS',objetivo='100.00',fecha_objetivo=None)|changes

    def test_valid_target_and_optional_date(self):
        self.assertEqual(GoalInput(**self.payload(objetivo='0.10')).objetivo,Decimal('0.10'))
        self.assertEqual(GoalInput(**self.payload(fecha_objetivo='2027-01-01')).fecha_objetivo,date(2027,1,1))

    def test_rejects_invalid_money_dates_and_ownership(self):
        for changes in [dict(objetivo=1.2),dict(objetivo='0'),dict(objetivo='1.001'),dict(objetivo='1e2'),
                        dict(fecha_objetivo='2026-02-30'),dict(moneda='XXX'),dict(usuario_id=str(uuid4())),
                        dict(cuenta_id='00000000-0000-0000-0000-000000000000')]:
            with self.subTest(changes=changes),self.assertRaises(ValidationError):GoalInput(**self.payload(**changes))

    def test_edit_cannot_reassign_account_currency_or_use_boolean_version(self):
        data=dict(nombre='Casa',objetivo='200',fecha_objetivo=None,version=0,archivada=False)
        for changes in [dict(cuenta_id=str(uuid4())),dict(moneda='USD'),dict(version=True),dict(archivada=1)]:
            with self.subTest(changes=changes),self.assertRaises(ValidationError):GoalEdit(**(data|changes))

    def row(self,**changes):
        return dict(id=uuid4(),espacio_id=uuid4(),cuenta_id=uuid4(),cuenta_nombre='Ahorros',nombre='Vacaciones',
                    moneda='ARS',objetivo=Decimal('100'),fecha_objetivo=date(2026,11,1),
                    archivada=False,version=0,saldo=Decimal('25'))|changes

    def test_progress_remaining_and_overdue_are_derived(self):
        value=public_goal(self.row(),date(2026,11,17))
        self.assertEqual((value['acumulado'],value['faltante'],value['porcentaje']),('25.00','75.00','25.0'))
        self.assertTrue(value['vencida']);self.assertFalse(value['alcanzada'])

    def test_negative_and_excess_do_not_break_progress(self):
        for saldo,saved,remaining,percentage,reached in [('-5','0.00','100.00','0.0',False),('110','110.00','0.00','100.0',True)]:
            value=public_goal(self.row(saldo=Decimal(saldo)),date(2026,11,17))
            self.assertEqual((value['acumulado'],value['faltante'],value['porcentaje'],value['alcanzada']),(saved,remaining,percentage,reached))
        self.assertFalse(public_goal(self.row(archivada=True),date(2026,11,17))['vencida'])

    def test_rounding_never_claims_completion_early(self):
        value=public_goal(self.row(saldo=Decimal('99.99')),date(2026,11,17))
        self.assertEqual(value['porcentaje'],'99.9');self.assertFalse(value['alcanzada'])

    def test_authentication(self):
        app=FastAPI();app.include_router(router);client=TestClient(app);path=f'/spaces/{uuid4()}/savings-goals'
        self.assertEqual(client.get(path).status_code,401)
        self.assertEqual(client.post(path,json=self.payload()).status_code,401)
        self.assertEqual(client.patch(path+'/'+str(uuid4()),json=dict(nombre='Casa',objetivo='200',version=0,archivada=False)).status_code,401)
