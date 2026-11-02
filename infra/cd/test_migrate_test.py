import contextlib
import io
import unittest
from unittest.mock import patch

import migrate_test as subject


class MigrationRunnerTests(unittest.TestCase):
    def env(self):
        return {'GITHUB_ACTIONS':'true','GITHUB_EVENT_NAME':'push',
                'GITHUB_REF':'refs/heads/main','GITHUB_REPOSITORY':'aleharo2003/gastos',
                'GITHUB_SHA':'a'*40,'SUPABASE_MIGRATOR_PASSWORD':'fake-password',
                'SUPABASE_DB_CA_CERT':'fake-certificate'}

    def test_only_expected_push_is_accepted(self):
        subject.authorized_environment(self.env())
        for key, value in [('GITHUB_ACTIONS',''),('GITHUB_EVENT_NAME','pull_request'),
                           ('GITHUB_REF','refs/heads/feature/x'),('GITHUB_REPOSITORY','other/repo'),
                           ('GITHUB_SHA','short')]:
            with self.subTest(key=key):
                env=self.env();env[key]=value
                with self.assertRaises(subject.MigrationError):
                    subject.authorized_environment(env)

    def test_missing_secret_is_rejected_without_echo(self):
        for key in ('SUPABASE_MIGRATOR_PASSWORD','SUPABASE_DB_CA_CERT'):
            env=self.env();env[key]=''
            with self.assertRaises(subject.MigrationError) as caught:
                subject.authorized_environment(env)
            self.assertNotIn('fake-password',str(caught.exception))

    def test_url_preserves_password_and_requires_verified_tls(self):
        password='fake@:/?#% secret'
        url=subject.connection_url(password,'/tmp/certificate.crt')
        self.assertEqual(url.password,password)
        self.assertEqual(url.username,'app_migrator.cyxhyfbiacfayixbmotq')
        self.assertEqual(url.host,'aws-1-us-west-2.pooler.supabase.com')
        self.assertEqual(url.port,5432)
        self.assertEqual(url.query['sslmode'],'verify-full')
        self.assertEqual(url.query['sslrootcert'],'/tmp/certificate.crt')

    def test_local_run_does_not_connect(self):
        with patch.dict(subject.os.environ,{},clear=True), patch.object(subject.sys,'argv',['migrate_test.py']), \
                patch.object(subject,'create_migration_engine') as factory, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(subject.main(),1)
            factory.assert_not_called()

    def test_bad_certificate_does_not_connect_or_leak(self):
        output=io.StringIO()
        with patch.dict(subject.os.environ,self.env(),clear=True), patch.object(subject.sys,'argv',['migrate_test.py']), \
                patch.object(subject,'create_migration_engine') as factory, contextlib.redirect_stderr(output):
            self.assertEqual(subject.main(),1)
            factory.assert_not_called()
        self.assertNotIn('fake-password',output.getvalue())
        self.assertNotIn('fake-certificate',output.getvalue())

    def test_driver_error_is_not_echoed(self):
        output=io.StringIO()
        with patch.dict(subject.os.environ,self.env(),clear=True), patch.object(subject.sys,'argv',['migrate_test.py']), \
                patch.object(subject.ssl,'SSLContext'), patch.object(subject,'create_migration_engine',side_effect=RuntimeError('fake-password')), \
                contextlib.redirect_stderr(output):
            self.assertEqual(subject.main(),1)
        self.assertNotIn('fake-password',output.getvalue())


if __name__ == '__main__':
    unittest.main()
