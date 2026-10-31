"""Real plan refresh and HTTP -> Redis -> Celery -> PostgreSQL integration.

Opt-in only against the disposable stack selected by VAGOU_TEST_URL and
DATABASE_URL. This test owns and stops its child worker and fixture data.
"""
import asyncio
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

import httpx


async def automation_fixture(operation, fixture):
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.config import settings
    from app.models import Job, User
    from app.passwords import hash_password
    from app.security import token

    engine = create_async_engine(settings().database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions.begin() as db:
            if operation == 'seed':
                common = {'name': 'Automation API fixture', 'email_verified': True,
                          'password_hash': hash_password(fixture['password']), 'privacy_version': '2026-01'}
                owner = User(id=fixture['owner'], email=f'{fixture["owner"]}@example.com', role='recruiter', **common)
                candidate = User(id=fixture['candidate'], email=fixture['email'], role='candidate',
                                 skills=['python'], is_premium=False, **common)
                free = User(id=fixture['free'], email=f'{fixture["free"]}@example.com', role='candidate', **common)
                db.add_all([owner, candidate, free])
                await db.flush()
                base = {'recruiter_id': owner.id, 'title': fixture['title'], 'company': 'API integration',
                        'description': 'Desenvolvimento Python com testes e processos profissionais.',
                        'salary_min': 6000, 'salary_max': 9000, 'modality': 'hybrid',
                        'location': 'São Paulo, SP', 'keywords': ['python'], 'moderation_status': 'approved', 'active': True}
                db.add_all([
                    Job(id=fixture['matching_job'], **base),
                    Job(**{**base, 'location': 'Rio de Janeiro / RJ'}),
                    Job(**{**base, 'salary_min': 25000, 'salary_max': 35000}),
                    Job(**{**base, 'moderation_status': 'pending'}),
                    Job(**{**base, 'title': 'Marketing profissional'}),
                ])
                return {'candidate': token(candidate), 'free': token(free)}
            if operation == 'cleanup':
                await db.execute(delete(User).where(User.id.in_([fixture['candidate'], fixture['free'], fixture['owner']])))
                return
            raise AssertionError('Unknown fixture operation')
    finally:
        await engine.dispose()


@unittest.skipUnless(os.getenv('VAGOU_TEST_URL'), 'Disposable API/Celery stack not configured')
class AutomationApiContract(unittest.TestCase):
    def test_plan_refresh_and_real_candidate_scoped_worker(self):
        from pypdf import PdfWriter
        from app.config import settings
        from app.manage_premium import set_premium

        candidate_id = uuid.uuid4()
        fixture = {'owner': uuid.uuid4(), 'candidate': candidate_id, 'free': uuid.uuid4(),
                   'matching_job': uuid.uuid4(), 'title': f'Python API {uuid.uuid4()}',
                   'email': f'{candidate_id}@example.com', 'password': 'Disposable-API-Worker-Password!'}
        worker = None
        preferences = {'titles': [fixture['title']], 'min_salary': 5000, 'max_salary': 10000,
                       'modalities': ['hybrid', 'onsite'], 'locations': ['São Paulo / SP'],
                       'automation_enabled': True, 'automation_interval_minutes': 60,
                       'automation_max_applications_per_run': 20}
        try:
            tokens = asyncio.run(automation_fixture('seed', fixture))
            candidate = {'Authorization': 'Bearer ' + tokens['candidate']}
            free = {'Authorization': 'Bearer ' + tokens['free']}
            with httpx.Client(base_url=os.environ['VAGOU_TEST_URL'], timeout=20) as client:
                current = client.get('/v1/me', headers=candidate)
                self.assertEqual(current.status_code, 200)
                self.assertFalse(current.json()['entitlements']['can_automate'])
                denied = client.put('/v1/me/preferences', headers=candidate, json=preferences)
                self.assertEqual(denied.status_code, 403, denied.text)
                asyncio.run(set_premium(fixture['email'], True))
                # The same JWT must observe an operator-side plan change immediately.
                current = client.get('/v1/me', headers=candidate)
                self.assertTrue(current.json()['is_premium'])
                self.assertTrue(current.json()['entitlements']['can_automate'])
                self.assertEqual(current.json()['entitlements']['plan'], 'premium')
                writer, pdf = PdfWriter(), io.BytesIO()
                writer.add_blank_page(width=200, height=200)
                writer.write(pdf)
                uploaded = client.put('/v1/me/resume', headers=candidate,
                                      files={'file': ('fixture.pdf', pdf.getvalue(), 'application/pdf')})
                self.assertEqual(uploaded.status_code, 200, uploaded.text)
                response = client.put('/v1/me/preferences', headers=candidate, json=preferences)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['max_salary'], 10000)
                self.assertTrue(response.json()['entitlements']['can_automate'])
                self.assertEqual(client.post('/v1/automation/run', headers=free).status_code, 403)
                queued = client.post('/v1/automation/run', headers=candidate)
                self.assertEqual(queued.status_code, 202, queued.text)
                self.assertEqual(queued.json()['status'], 'queued')
                self.assertFalse(queued.json()['deduplicated'])
                repeated = client.post('/v1/automation/run', headers=candidate)
                self.assertEqual(repeated.status_code, 202, repeated.text)
                self.assertTrue(repeated.json()['deduplicated'])

                # No beat or mocked task delivery: this child consumes the actual broker message.
                with tempfile.TemporaryFile(mode='w+') as worker_output:
                    worker = subprocess.Popen(
                        [sys.executable, '-m', 'celery', '-A', 'app.worker:celery', 'worker',
                         '--pool=solo', '--concurrency=1', '--loglevel=WARNING',
                         '--without-gossip', '--without-mingle', '--without-heartbeat'],
                        cwd=Path(__file__).resolve().parents[1], env=os.environ.copy(),
                        stdout=worker_output, stderr=worker_output,
                    )
                    deadline = time.monotonic() + 15
                    run = None
                    while time.monotonic() < deadline:
                        self.assertIsNone(worker.poll(), 'Fixture Celery worker exited before handling its task')
                        response = client.get('/v1/automation/runs', headers=candidate)
                        self.assertEqual(response.status_code, 200, response.text)
                        completed = [item for item in response.json()['items'] if item['status'] == 'complete']
                        if completed:
                            run = completed[0]
                            break
                        time.sleep(0.25)
                    self.assertIsNotNone(run, 'Real worker did not persist a completed candidate run within 15 seconds')
                    self.assertEqual(run['submitted_applications'], 1)
                    self.assertEqual(run['eligible_jobs'], 1)
                    events = client.get(f'/v1/automation/runs/{run["id"]}/events', headers=candidate)
                    self.assertEqual(events.status_code, 200, events.text)
                    sent = [item for item in events.json()['items'] if item['status'] == 'submitted']
                    self.assertEqual(len(sent), 1)
                    self.assertEqual(sent[0]['job_id'], str(fixture['matching_job']))
                    rows = client.get('/v1/applications', headers=candidate).json()
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0]['source'], 'automatic')
                    self.assertEqual(rows[0]['job_id'], str(fixture['matching_job']))
                    self.assertEqual(client.get('/v1/applications', headers=free).json(), [])
                    # Revocation is equally authoritative and disables future automation.
                    asyncio.run(set_premium(fixture['email'], False))
                    current = client.get('/v1/me', headers=candidate).json()
                    self.assertFalse(current['entitlements']['can_automate'])
                    self.assertFalse(current['automation_enabled'])
                    self.assertEqual(client.post('/v1/automation/run', headers=candidate).status_code, 403)
                    worker.terminate()
                    worker.wait(timeout=10)
                    worker = None
        finally:
            if worker is not None:
                worker.terminate()
                try:
                    worker.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait(timeout=5)
            asyncio.run(automation_fixture('cleanup', fixture))
            # Direct fixture deletion cannot perform the application's PDF file cleanup.
            (settings().storage_dir / str(candidate_id)).unlink(missing_ok=True)
