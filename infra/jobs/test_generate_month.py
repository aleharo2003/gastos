import contextlib
import io
import os
import unittest
from unittest.mock import MagicMock,patch
import generate_month


class GenerationTests(unittest.TestCase):
    def connection(self,identity=None,count=3):
        connection=MagicMock()
        cursor=connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect=[identity or ('app_jobs','app_jobs',False,False,False,False,False,False,0),(count,)]
        return connection,cursor

    def test_calls_only_fixed_function_and_confirms_transaction(self):
        connection,cursor=self.connection()
        connector=MagicMock();connector.return_value.__enter__.return_value=connection
        with patch.dict(os.environ,{'JOBS_DATABASE_URL':'private-dsn'}):
            self.assertEqual(generate_month.generate(connector),3)
        self.assertEqual(cursor.execute.call_args_list[-1].args,('SELECT public.generar_cuotas_mes()',))
        self.assertEqual(connector.return_value.__exit__.call_args.args,(None,None,None))

    def test_rejects_runtime_or_privileged_identity(self):
        for identity in [('app_runtime','app_runtime',False,False,False,False,False,False,0),
                         ('app_jobs','app_jobs',False,True,False,False,False,False,0)]:
            connection,cursor=self.connection(identity)
            connector=MagicMock();connector.return_value.__enter__.return_value=connection
            with patch.dict(os.environ,{'JOBS_DATABASE_URL':'private-dsn'}),self.assertRaises(RuntimeError):
                generate_month.generate(connector)
            self.assertEqual(cursor.execute.call_count,1)

    def test_no_credentials_or_traceback_on_failure(self):
        output=io.StringIO()
        with patch.object(generate_month,'generate',side_effect=Exception('password=secret-host')),contextlib.redirect_stderr(output):
            self.assertEqual(generate_month.main(),1)
        self.assertNotIn('secret-host',output.getvalue())
        self.assertNotIn('Traceback',output.getvalue())
