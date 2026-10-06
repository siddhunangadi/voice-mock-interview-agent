import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_does_not_expose_config(self):
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_rejects_invalid_interview_without_calling_providers(self):
        response = self.client.post('/api/interviews', json={'job_description': '   ', 'resume': 'a'})
        self.assertEqual(response.status_code, 422)
        response = self.client.post('/api/interviews', json={'job_description': ' ' * 40, 'resume': ' ' * 40})
        self.assertEqual(response.status_code, 422)

    def test_malformed_authenticated_events_are_validation_errors(self):
        with patch.dict('os.environ', {'VAPI_SERVER_TOKEN': 'test-token'}):
            for message in ['invalid', {'call': []}, {'type': 'end-of-call-report', 'call': {'id': 'invalid'}}]:
                response = self.client.post('/vapi/events', json={'message': message},
                                            headers={'Authorization': 'Bearer test-token'})
                self.assertEqual(response.status_code, 422)

    def test_voice_endpoint_requires_provider_authentication(self):
        response = self.client.post('/vapi/chat/completions', json={'messages': [{'role': 'user', 'content': 'hello'}]})
        self.assertEqual(response.status_code, 401)
        response = self.client.post('/vapi/events', json={'message': {'type': 'status-update'}})
        self.assertEqual(response.status_code, 401)

    def test_call_proxy_never_accepts_arbitrary_assistant_config(self):
        response = self.client.post('/voice/call/web', json={'assistant': {'model': {'url': 'https://evil.example'}}})
        self.assertIn(response.status_code, (400, 401, 422))


if __name__ == '__main__':
    unittest.main()
