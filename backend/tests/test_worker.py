"""Premium automation contracts against the disposable integration PostgreSQL."""
import asyncio
import os
import unittest
import uuid


@unittest.skipUnless(os.getenv('VAGOU_TEST_URL'), 'Disposable integration stack not configured; worker NOT executed')
class AutomationContract(unittest.TestCase):
    def test_verified_consent_moderation_idempotency_and_truthful_events(self):
        async def scenario():
            from datetime import datetime, timedelta, timezone
            from sqlalchemy import delete, select, update
            from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
            from app.automation_models import AutomationEvent, AutomationRun
            from app.config import settings
            from app.models import Application, Job, User
            from app.passwords import hash_password
            from app.worker import automate

            engine = create_async_engine(settings().database_url)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            owner = uuid.uuid4()
            ids = [uuid.uuid4() for _ in range(5)]
            job_ids = [uuid.uuid4() for _ in range(5)]
            external = uuid.uuid4()
            try:
                async with sessions.begin() as db:
                    common = {'name': 'Automation test', 'password_hash': hash_password('Automation-Test-Password!'),
                              'privacy_version': '2026-01'}
                    db.add(User(id=owner, email=f'{owner}@example.com', role='recruiter', email_verified=True, **common))
                    for index, candidate_id in enumerate(ids):
                        db.add(User(id=candidate_id, email=f'{candidate_id}@example.com', role='candidate',
                            email_verified=index != 3, is_premium=index != 1, automation_enabled=index != 2,
                            skills=['python', 'sql', 'docker'], resume_key=str(candidate_id) if index != 4 else None,
                            preferences={'titles': [str(owner)]}, **common))
                    await db.flush()
                    fixture = {'recruiter_id': owner, 'title': str(owner), 'company': 'Automation fixture',
                        'description': 'A fixture for automation eligibility and thresholds.', 'salary_min': 1000,
                        'salary_max': 5000, 'modality': 'remote', 'location': 'Brasil'}
                    for job_id, keywords, status, active in zip(job_ids,
                            [['python', 'sql'], ['python', 'sql', 'docker', 'redis'], ['python'], ['python'], ['python']],
                            ['approved', 'approved', 'pending', 'rejected', 'approved'], [True, True, True, True, False]):
                        db.add(Job(id=job_id, keywords=keywords, moderation_status=status, active=active, **fixture))
                    db.add(Job(id=external, **{**fixture, 'recruiter_id': None}, keywords=['python'],
                        moderation_status='approved', source_name='CI partner', source_external_id=str(external),
                        source_url=f'https://example.com/jobs/{external}'))
                await automate()
                await automate()  # Beat can run every minute, candidate cadence must not.
                async with sessions() as db:
                    initial_runs = list((await db.scalars(select(AutomationRun).where(AutomationRun.candidate_id.in_(ids)))).all())
                    self.assertEqual(len(initial_runs), 2)
                async with sessions.begin() as db:
                    await db.execute(update(AutomationRun).where(AutomationRun.candidate_id.in_(ids))
                        .values(started_at=datetime.now(timezone.utc) - timedelta(hours=2)))
                await automate()  # A new due cycle must preserve application uniqueness.
                await automate()  # The new completed cycle again postpones the next run.
                async with sessions() as db:
                    applications = list((await db.scalars(select(Application).where(Application.candidate_id.in_(ids)))).all())
                    self.assertEqual(len(applications), 1)
                    self.assertEqual(applications[0].candidate_id, ids[0])
                    self.assertEqual(applications[0].job_id, job_ids[0])
                    self.assertEqual(applications[0].source, 'automatic')
                    self.assertEqual(applications[0].match_score, 100)
                    runs = list((await db.scalars(select(AutomationRun).where(AutomationRun.candidate_id.in_(ids)))).all())
                    self.assertEqual(len(runs), 4)
                    self.assertEqual({run.candidate_id for run in runs}, {ids[0], ids[4]})
                    self.assertTrue(all(run.status == 'complete' and run.finished_at for run in runs))
                    events = list((await db.scalars(select(AutomationEvent).where(AutomationEvent.run_id.in_([run.id for run in runs])))).all())
                    self.assertEqual(sum(event.status == 'submitted' for event in events), 1)
                    self.assertEqual(sum(event.status == 'already_applied' for event in events), 1)
                    self.assertEqual(sum(event.status == 'requires_manual' for event in events), 2)
                    self.assertEqual(sum(event.status == 'missing_resume' for event in events), 2)
                    self.assertTrue(all(event.job_id == external for event in events if event.status == 'requires_manual'))
            finally:
                async with sessions.begin() as db:
                    await db.execute(delete(Job).where(Job.id == external))
                    await db.execute(delete(User).where(User.id.in_([owner, *ids])))
                await engine.dispose()
        asyncio.run(scenario())
