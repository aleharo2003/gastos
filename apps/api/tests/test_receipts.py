import unittest
from unittest.mock import patch
from uuid import uuid4
import httpx
from fastapi import HTTPException, FastAPI
from fastapi.testclient import TestClient
from app.receipts import router, file_type
from app.receipt_storage import ReceiptStorage, MAX_BYTES

class ReceiptsTests(unittest.TestCase):
    def test_signatures(self):
        self.assertEqual(file_type(b'%PDF-1.7\n%%EOF')[0],'application/pdf')
        self.assertEqual(file_type(b'\xff\xd8\xffdata\xff\xd9')[0],'image/jpeg')
        self.assertEqual(file_type(b'\x89PNG\r\n\x1a\ndataIEND\xaeB`\x82')[0],'image/png')
        for data in (b'',b'<svg/>',b'<html/>',b'fake.pdf',b'%PDF-broken'):
            with self.assertRaises(HTTPException):file_type(data)

    def test_routes_require_authentication(self):
        app=FastAPI();app.include_router(router);client=TestClient(app)
        path=f'/spaces/{uuid4()}/accounts/{uuid4()}/expenses/{uuid4()}/receipts'
        self.assertEqual(client.get(path).status_code,401)
        self.assertEqual(client.post(path+'/'+str(uuid4()),content=b'x').status_code,401)
        self.assertEqual(client.get(path+'/'+str(uuid4())+'/file').status_code,401)

    def storage(self,handler):
        with patch.dict('os.environ',{'AUTH_SUPABASE_PROJECT_REF':'a'*20,'APP_STORAGE_SERVICE_KEY':'sb_secret_test'}):s=ReceiptStorage()
        s.client=lambda:httpx.Client(transport=httpx.MockTransport(handler),headers=s.headers)
        return s

    def test_public_bucket_fails_closed(self):
        calls=[]
        def handler(req):calls.append(req.url.path);return httpx.Response(200,json={'public':True})
        with self.assertRaises(HTTPException) as error:self.storage(handler).put('object',b'data','image/png')
        self.assertEqual(error.exception.status_code,503);self.assertEqual(len(calls),1)

    def test_private_upload_uses_key_only_on_server(self):
        calls=[]
        def handler(req):
            calls.append(req)
            return httpx.Response(200,json={'public':False} if '/bucket/' in req.url.path else {'Key':'object'})
        self.storage(handler).put('space/expense/file',b'data','image/png')
        self.assertEqual(calls[1].content,b'data');self.assertEqual(calls[1].headers['apikey'],'sb_secret_test')
        self.assertNotIn('authorization',calls[1].headers)

    def test_failed_storage_does_not_expose_body(self):
        def handler(req):return httpx.Response(403,text='private-token-secret')
        with self.assertRaises(HTTPException) as error:self.storage(handler).get('object')
        self.assertNotIn('private-token',str(error.exception))

    def test_download_limit(self):
        def handler(req):return httpx.Response(200,json={'public':False}) if '/bucket/' in req.url.path else httpx.Response(200,content=b'x'*(MAX_BYTES+1))
        with self.assertRaises(HTTPException):self.storage(handler).get('object')
