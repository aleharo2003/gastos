import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import Mock,patch
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.expenses import expense_summary,router

class SummaryTests(unittest.TestCase):
    def test_public_routes_require_identity(self):
        app=FastAPI();app.include_router(router);client=TestClient(app);space=uuid4()
        for suffix in ['expenses','expense-summary']:
            self.assertEqual(client.get(f'/spaces/{space}/{suffix}').status_code,401)

    @patch('app.expenses.require_member')
    def test_december_bounds_and_decimal_serialization(self,_):
        session=Mock();session.execute.return_value.mappings.return_value.all.return_value=[{'moneda':'ARS','dia':Decimal('0.10'),'mes':Decimal('9007199254740993.01')}]
        result=expense_summary(session,uuid4(),uuid4(),day=date(2026,12,31))
        params=session.execute.call_args.args[1]
        self.assertEqual(params['f'],date(2026,12,1));self.assertEqual(params['u'],date(2027,1,1))
        self.assertEqual(result['totales'][0]['mes'],'9007199254740993.01')
