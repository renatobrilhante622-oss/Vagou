"""Automation test uses the same disposable DB as the API contract suite."""
import asyncio
import os
import unittest
import uuid


@unittest.skipUnless(os.getenv('VAGOU_TEST_URL'), 'Disposable integration stack not configured; worker NOT executed')
class AutomationContract(unittest.TestCase):
    def test_premium_consent_threshold_and_idempotency(self):
        async def scenario():
            from sqlalchemy import delete, select
            from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
            from app.config import settings
            from app.models import Application, Job, User
            from app.passwords import hash_password
            from app.worker import automate

            engine = create_async_engine(settings().database_url)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            owner = uuid.uuid4()
            ids = [uuid.uuid4() for _ in range(3)]
            job_ids = [uuid.uuid4(), uuid.uuid4()]
            try:
                async with sessions.begin() as db:
                    common = {'name': 'Automation test', 'password_hash': hash_password('Automation-Test-Password!'), 'privacy_version': '2026-01'}
                    db.add(User(id=owner, email=f'{owner}@example.com', role='recruiter', **common))
                    for index, candidate_id in enumerate(ids):
                        db.add(User(id=candidate_id, email=f'{candidate_id}@example.com', role='candidate',
                                    is_premium=index != 1, automation_enabled=index != 2,
                                    skills=['python', 'sql', 'docker'], resume_key=str(candidate_id),
                                    preferences={'titles': [str(owner)]}, **common))
                    await db.flush()
                    for job_id, keywords in zip(job_ids, [['python', 'sql'], ['python', 'sql', 'docker', 'redis']]):
                        db.add(Job(id=job_id, recruiter_id=owner, title=str(owner), company='Automation fixture', description='A fixture for automation eligibility and thresholds.', salary_min=1000, salary_max=5000, modality='remote', location='Brasil', keywords=keywords))
                await automate()
                await automate()
                async with sessions() as db:
                    rows = list((await db.scalars(select(Application).where(Application.candidate_id.in_(ids)))).all())
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0].candidate_id, ids[0])
                    self.assertEqual(rows[0].job_id, job_ids[0])
                    self.assertEqual(rows[0].source, 'automatic')
                    self.assertEqual(rows[0].match_score, 100)
            finally:
                async with sessions.begin() as db:
                    await db.execute(delete(User).where(User.id.in_([owner, *ids])))
                await engine.dispose()
        asyncio.run(scenario())