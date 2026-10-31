"""Public contracts against a disposable API/PostgreSQL/Redis stack.

VAGOU_TEST_URL opts into integration tests. DATABASE_URL must point to that same
throwaway stack. OTPs are read only from fixtures' encrypted outbox rows, never
returned by a production API or printed. No SMTP account is required in CI.
"""
import asyncio
import io
import os
import unittest
import uuid

import httpx


async def fixture_database(operation, *arguments):
    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.config import settings
    from app.models import EmailOutbox, User
    from app.passwords import hash_password
    from app.security import cipher, token

    engine = create_async_engine(settings().database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions.begin() as db:
            if operation == 'code':
                row = await db.scalar(select(EmailOutbox).join(User, User.id == EmailOutbox.user_id)
                    .where(User.email == arguments[0]).order_by(EmailOutbox.created_at.desc()).limit(1))
                if row is None:
                    raise AssertionError('Fixture did not create a durable verification message')
                return cipher().decrypt(row.code_encrypted.encode()).decode()
            if operation == 'moderator':
                email = arguments[0]
                if email not in settings().moderator_emails:
                    raise AssertionError('Configure MODERATOR_EMAILS to include moderator-ci@example.com for integration tests')
                moderator = User(email=email, name='CI moderator', role='candidate', email_verified=True,
                    password_hash=hash_password('Disposable-Moderator-Password!'), privacy_version='2026-01')
                db.add(moderator)
                await db.flush()
                return token(moderator)
            if operation == 'cleanup':
                await db.execute(delete(User).where(User.email.in_(arguments[0])))
                return None
            raise AssertionError('Unknown fixture operation')
    finally:
        await engine.dispose()


@unittest.skipUnless(os.getenv('VAGOU_TEST_URL'), 'VAGOU_TEST_URL not configured; integration suite NOT executed')
class ApiContract(unittest.TestCase):
    def test_verified_candidate_moderated_recruiter_lifecycle(self):
        from pypdf import PdfWriter

        password = 'Integration-only-Strong-192!'
        emails = {role: f'{uuid.uuid4().hex}@example.com' for role in ['candidate', 'recruiter']}
        moderator_email = 'moderator-ci@example.com'
        headers = {}
        try:
            moderator_token = asyncio.run(fixture_database('moderator', moderator_email))
            moderator = {'Authorization': 'Bearer ' + moderator_token}
            with httpx.Client(base_url=os.environ['VAGOU_TEST_URL'], timeout=20) as client:
                self.assertEqual(client.get('/health/ready').status_code, 200)
                for role, email in emails.items():
                    registration = {'email': email, 'name': role, 'password': password, 'role': role,
                                    'privacy_version': '2026-01', 'consent': True}
                    if role == 'recruiter':
                        registration.update(company_cnpj='11222333000181', company_name='Integration Ltda',
                            company_contact_email=email, company_phone='+5511999999999')
                    response = client.post('/v1/auth/register', json=registration)
                    self.assertEqual(response.status_code, 201, response.text)
                    self.assertFalse(response.json()['email_verified'])
                    self.assertNotIn('code', response.json())
                    code = asyncio.run(fixture_database('code', email))
                    self.assertEqual(len(code), 6)
                    if role == 'candidate':
                        denied = client.post('/v1/auth/login', json={'email': email, 'password': password})
                        self.assertEqual(denied.status_code, 403, denied.text)
                        wrong = str((int(code) + 1) % 1000000).zfill(6)
                        self.assertEqual(client.post('/v1/auth/verify-email', json={'email': email, 'code': wrong}).status_code, 400)
                    response = client.post('/v1/auth/verify-email', json={'email': email, 'code': code})
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertTrue(response.json()['verified'])
                    if role == 'candidate':
                        self.assertEqual(client.post('/v1/auth/verify-email', json={'email': email, 'code': code}).status_code, 400)
                    response = client.post('/v1/auth/login', json={'email': email, 'password': password})
                    self.assertEqual(response.status_code, 200, response.text)
                    headers[role] = {'Authorization': 'Bearer ' + response.json()['access_token']}

                candidate, recruiter = headers['candidate'], headers['recruiter']
                payload = {'title': 'Python Engineer', 'company': 'Integration',
                    'description': 'Desenvolvimento de APIs Python com PostgreSQL e testes.',
                    'salary_min': 5000, 'salary_max': 8000, 'modality': 'remote',
                    'location': 'Brasil', 'keywords': ['python', 'sql']}
                self.assertEqual(client.post('/v1/jobs', headers=candidate, json=payload).status_code, 403)
                response = client.post('/v1/jobs', headers=recruiter, json=payload)
                self.assertEqual(response.status_code, 201, response.text)
                job = response.json()['id']
                self.assertEqual(response.json()['moderation_status'], 'pending')
                self.assertEqual(client.get(f'/v1/jobs/{job}').status_code, 404)
                self.assertNotIn(job, [row['id'] for row in client.get('/v1/jobs').json()])
                owner_jobs = client.get('/v1/recruiter/jobs', headers=recruiter)
                self.assertEqual(owner_jobs.status_code, 200, owner_jobs.text)
                self.assertIn(job, [row['id'] for row in owner_jobs.json()])
                self.assertEqual(client.patch(f'/v1/moderation/jobs/{job}', headers=recruiter,
                    json={'status': 'approved'}).status_code, 403)
                response = client.patch(f'/v1/moderation/jobs/{job}', headers=moderator,
                    json={'status': 'approved', 'note': 'Vaga revisada na suíte de integração.'})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(client.get(f'/v1/jobs/{job}').status_code, 200)
                self.assertEqual(client.put('/v1/me/preferences', headers=candidate,
                    json={'automation_enabled': True}).status_code, 403)
                self.assertEqual(client.put('/v1/me/profile', headers=candidate,
                    json={'name': 'Candidato', 'skills': ['python', 'sql'], 'phone': '+5511999999999'}).status_code, 200)
                self.assertEqual(client.post(f'/v1/jobs/{job}/applications', headers=candidate).status_code, 409)
                pdf = io.BytesIO()
                writer = PdfWriter()
                writer.add_blank_page(width=200, height=200)
                writer.write(pdf)
                self.assertEqual(client.put('/v1/me/resume', headers=candidate,
                    files={'file': ('cv.pdf', pdf.getvalue(), 'application/pdf')}).status_code, 200)
                self.assertEqual(client.get('/v1/me/resume', headers=candidate).content, pdf.getvalue())
                self.assertEqual(client.put('/v1/me/resume', headers=candidate,
                    files={'file': ('bad.pdf', b'not a pdf', 'application/pdf')}).status_code, 422)
                response = client.post(f'/v1/jobs/{job}/applications', headers=candidate)
                self.assertEqual(response.status_code, 200, response.text)
                application = response.json()['id']
                self.assertTrue(response.json()['created'])
                duplicate = client.post(f'/v1/jobs/{job}/applications', headers=candidate)
                self.assertFalse(duplicate.json()['created'])
                self.assertEqual(client.get(f'/v1/applications/{application}/resume', headers=recruiter).content, pdf.getvalue())
                self.assertEqual(client.patch(f'/v1/applications/{application}', headers=candidate,
                    json={'status': 'hired'}).status_code, 403)
                self.assertEqual(client.patch(f'/v1/applications/{application}', headers=recruiter,
                    json={'status': 'interview'}).status_code, 200)
                report = client.get('/v1/dashboard', headers=candidate).json()
                self.assertEqual(report['total_applications'], 1)
                self.assertEqual(report['manual'], 1)
                self.assertEqual(report['average_match_score'], 100)
                self.assertEqual(report['by_status'], {'interview': 1})
                self.assertEqual(client.request('DELETE', '/v1/me', headers=candidate,
                    json={'password': 'wrong'}).status_code, 401)
                for role in ['candidate', 'recruiter']:
                    response = client.request('DELETE', '/v1/me', headers=headers[role], json={'password': password})
                    self.assertEqual(response.status_code, 204, response.text)
                    self.assertEqual(client.get('/v1/me', headers=headers[role]).status_code, 401)
        finally:
            asyncio.run(fixture_database('cleanup', [*emails.values(), moderator_email]))
