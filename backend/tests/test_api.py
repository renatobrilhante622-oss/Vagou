"""Integration contract against a running disposable stack.
Run VAGOU_TEST_URL=http://127.0.0.1:8000 python -m unittest discover -s tests -v.
Requires PostgreSQL migrations, Redis and the API; creates and deletes its own data.
"""
import io
import os
import unittest
import uuid

import httpx


@unittest.skipUnless(os.getenv('VAGOU_TEST_URL'), 'VAGOU_TEST_URL not configured; integration suite NOT executed')
class ApiContract(unittest.TestCase):
    def test_candidate_recruiter_lifecycle(self):
        from pypdf import PdfWriter
        password = 'Integration-only-Strong-192!'
        registered = []
        headers = {}
        with httpx.Client(base_url=os.environ['VAGOU_TEST_URL'], timeout=20) as client:
            self.assertEqual(client.get('/health/ready').status_code, 200)
            try:
                for role in ['candidate', 'recruiter']:
                    email = f'{uuid.uuid4().hex}@example.com'
                    response = client.post('/v1/auth/register', json={'email': email, 'name': role, 'password': password, 'role': role, 'privacy_version': '2026-01', 'consent': True})
                    self.assertEqual(response.status_code, 201, response.text)
                    registered.append(role)
                    response = client.post('/v1/auth/login', json={'email': email, 'password': password})
                    self.assertEqual(response.status_code, 200, response.text)
                    headers[role] = {'Authorization': 'Bearer ' + response.json()['access_token']}
                candidate, recruiter = headers['candidate'], headers['recruiter']
                payload = {'title': 'Python Engineer', 'company': 'Integration', 'description': 'Desenvolvimento de APIs Python com PostgreSQL e testes.', 'salary_min': 5000, 'salary_max': 8000, 'modality': 'remote', 'location': 'Brasil', 'keywords': ['python', 'sql']}
                self.assertEqual(client.post('/v1/jobs', headers=candidate, json=payload).status_code, 403)
                response = client.post('/v1/jobs', headers=recruiter, json=payload)
                self.assertEqual(response.status_code, 201, response.text)
                job = response.json()['id']
                self.assertEqual(client.put('/v1/me/preferences', headers=candidate, json={'automation_enabled': True}).status_code, 403)
                self.assertEqual(client.put('/v1/me/profile', headers=candidate, json={'name': 'Candidato', 'skills': ['python', 'sql'], 'phone': '+5511999999999'}).status_code, 200)
                self.assertEqual(client.post(f'/v1/jobs/{job}/applications', headers=candidate).status_code, 409)
                pdf = io.BytesIO()
                writer = PdfWriter()
                writer.add_blank_page(width=200, height=200)
                writer.write(pdf)
                self.assertEqual(client.put('/v1/me/resume', headers=candidate, files={'file': ('cv.pdf', pdf.getvalue(), 'application/pdf')}).status_code, 200)
                response = client.get('/v1/me/resume', headers=candidate)
                self.assertEqual(response.content, pdf.getvalue())
                self.assertEqual(client.put('/v1/me/resume', headers=candidate, files={'file': ('bad.pdf', b'not a pdf', 'application/pdf')}).status_code, 422)
                response = client.post(f'/v1/jobs/{job}/applications', headers=candidate)
                self.assertEqual(response.status_code, 200, response.text)
                application = response.json()['id']
                self.assertTrue(response.json()['created'])
                duplicate = client.post(f'/v1/jobs/{job}/applications', headers=candidate)
                self.assertFalse(duplicate.json()['created'])
                self.assertEqual(client.get(f'/v1/applications/{application}/resume', headers=recruiter).content, pdf.getvalue())
                self.assertEqual(client.patch(f'/v1/applications/{application}', headers=candidate, json={'status': 'hired'}).status_code, 403)
                self.assertEqual(client.patch(f'/v1/applications/{application}', headers=recruiter, json={'status': 'interview'}).status_code, 200)
                report = client.get('/v1/dashboard', headers=candidate).json()
                self.assertEqual(report['total_applications'], 1)
                self.assertEqual(report['manual'], 1)
                self.assertEqual(report['average_match_score'], 100)
                self.assertEqual(report['by_status'], {'interview': 1})
                self.assertEqual(client.request('DELETE', '/v1/me', headers=candidate, json={'password': 'wrong'}).status_code, 401)
            finally:
                for role in registered:
                    if role in headers:
                        response = client.request('DELETE', '/v1/me', headers=headers[role], json={'password': password})
                        self.assertEqual(response.status_code, 204, response.text)
                        self.assertEqual(client.get('/v1/me', headers=headers[role]).status_code, 401)
