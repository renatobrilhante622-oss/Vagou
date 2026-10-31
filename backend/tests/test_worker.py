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
                            preferences={'titles': [str(owner)], 'modalities': ['remote']}, **common))
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

    def test_targeted_force_scans_beyond_page_and_submission_cap(self):
        async def scenario():
            from datetime import datetime, timezone
            from sqlalchemy import delete, select
            from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
            from app.automation_models import AutomationEvent, AutomationRun
            from app.config import settings
            from app.models import Application, Job, User
            from app.passwords import hash_password
            from app.worker import automate

            engine = create_async_engine(settings().database_url)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            owner, first, second, malformed, unpaid = [uuid.uuid4() for _ in range(5)]
            # Contiguous UUIDs prove that qualifying jobs on the second page are scanned.
            prefix = uuid.uuid4().int & ~0xFFFF
            jobs = [uuid.UUID(int=prefix + i) for i in range(207)]
            title = f'Python {owner}'
            common = {'name': 'Targeted fixture', 'password_hash': hash_password('Targeted-fixture-password!'),
                      'privacy_version': '2026-01', 'email_verified': True}
            preferences = {'titles': [title], 'modalities': ['onsite'], 'locations': ['Recife / PE'],
                'min_salary': 5000, 'max_salary': 8000, 'automation_max_applications_per_run': 1}
            try:
                async with sessions.begin() as db:
                    db.add(User(id=owner, email=f'{owner}@example.com', role='recruiter', **common))
                    for candidate in [first, second, malformed, unpaid]:
                        db.add(User(id=candidate, email=f'{candidate}@example.com', role='candidate',
                            is_premium=candidate not in [unpaid, second], automation_enabled=True, resume_key=str(candidate),
                            preferences={} if candidate == malformed else preferences,
                            skills=['python'], **common))
                    await db.flush()
                    for i, job in enumerate(jobs):
                        fields = {'id': job, 'recruiter_id': owner, 'title': title, 'company': 'Targeted fixture',
                            'description': 'Vaga de teste com requisitos e critérios completos.', 'salary_min': 5000,
                            'salary_max': 7000, 'modality': 'onsite', 'location': 'RECIFE, Pernambuco',
                            'keywords': ['python'], 'active': i != 206,
                            'moderation_status': 'pending' if i == 205 else 'approved'}
                        if i == 0:
                            fields.update(salary_min=1000, salary_max=4000)
                        elif i == 1:
                            fields['location'] = 'Recife / BA'
                        elif i == 2:
                            fields['modality'] = 'hybrid'
                        elif i == 3:
                            fields['title'] = 'Outra área'
                        elif i == 4:
                            fields.update(salary_min=9000, salary_max=10000)
                        elif i == 5:
                            fields['keywords'] = ['java']
                        elif i == 7:
                            fields.update(recruiter_id=None, source_url=f'https://example.com/jobs/{job}',
                                source_name='Fixture', source_external_id=str(job))
                        db.add(Job(**fields))
                    db.add(AutomationRun(candidate_id=first, status='complete',
                        started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc)))
                # A scheduled targeted call honors cadence; force does not.
                self.assertEqual(await automate(candidate_id=str(first)), 0)
                self.assertEqual(await automate(candidate_id=str(first), force=True), 1)
                async with sessions() as db:
                    runs = list((await db.scalars(select(AutomationRun).where(AutomationRun.candidate_id.in_([first, second])))).all())
                    self.assertEqual(len(runs), 2)
                    actual = next(run for run in runs if run.scanned_jobs)
                    self.assertEqual(actual.scanned_jobs, 205)
                    self.assertEqual(actual.eligible_jobs, 199)
                    self.assertEqual(actual.submitted_applications, 1)
                    self.assertEqual(actual.manual_review_jobs, 1)
                    events = list((await db.scalars(select(AutomationEvent).where(AutomationEvent.run_id == actual.id))).all())
                    self.assertEqual(sum(event.status == 'limit_reached' for event in events), 197)
                    self.assertTrue(any(event.job_id == jobs[204] for event in events))
                # A second explicit cycle advances to the next vacancy, never duplicates a send.
                self.assertEqual(await automate(candidate_id=first, force=True), 1)
                self.assertEqual(await automate(candidate_id=first), 0)
                self.assertEqual(await automate(candidate_id=unpaid, force=True), 0)
                self.assertEqual(await automate(candidate_id=malformed, force=True), 0)
                async with sessions() as db:
                    applications = list((await db.scalars(select(Application).where(Application.candidate_id.in_([first, second, malformed, unpaid])))).all())
                    self.assertEqual(len(applications), 2)
                    self.assertEqual({row.candidate_id for row in applications}, {first})
                    self.assertEqual({row.job_id for row in applications}, {jobs[6], jobs[8]})
                    malformed_run = await db.scalar(select(AutomationRun).where(AutomationRun.candidate_id == malformed))
                    self.assertEqual(malformed_run.submitted_applications, 0)
                    criterion = await db.scalar(select(AutomationEvent.status).where(AutomationEvent.run_id == malformed_run.id))
                    self.assertEqual(criterion, 'criteria_missing')
                # Test access is explicit server configuration, never a mobile-supplied flag.
                self.assertEqual(await automate(candidate_id=second, force=True), 0)
                from unittest.mock import patch
                configured = settings().model_copy(update={'environment': 'test',
                    'premium_test_emails': [f'{second}@EXAMPLE.COM']})
                with patch('app.entitlements.settings', return_value=configured):
                    self.assertEqual(await automate(candidate_id=second, force=True), 1)
                production = configured.model_copy(update={'environment': 'production'})
                with patch('app.entitlements.settings', return_value=production):
                    self.assertEqual(await automate(candidate_id=second, force=True), 0)
                async with sessions() as db:
                    second_jobs = list((await db.scalars(select(Application.job_id).where(Application.candidate_id == second))).all())
                    self.assertEqual(second_jobs, [jobs[6]])
                with self.assertRaises(ValueError):
                    await automate(force=True)
            finally:
                async with sessions.begin() as db:
                    await db.execute(delete(Job).where(Job.id.in_(jobs)))
                    await db.execute(delete(User).where(User.id.in_([owner, first, second, malformed, unpaid])))
                await engine.dispose()
        asyncio.run(scenario())
