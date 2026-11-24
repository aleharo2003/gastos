import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from uuid import uuid4

from app.reminder_preferences import DEFAULTS, router


class ReminderPreferenceInputTests(unittest.TestCase):
    def test_invalid_fields_are_rejected_at_the_http_boundary(self):
        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as client:
            for invalid in (
                {'canal': 'sms'}, {'dias_anticipacion': True}, {'dias_anticipacion': 31},
                {'hora_local': '24:00'}, {'hora_local': '09:00Z'}, {'hora_local': '09:00:15'},
                {'vencimientos': 'true'}, {'usuario_id': str(uuid4())},
            ):
                with self.subTest(invalid=invalid):
                    response = client.put(f'/spaces/{uuid4()}/reminder-preferences',
                                          json=DEFAULTS | invalid)
                    self.assertEqual(response.status_code, 422)
