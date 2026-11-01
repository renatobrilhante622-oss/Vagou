"""Premium automation contracts against the disposable integration PostgreSQL."""
import asyncio
import os
import unittest
import uuid
from unittest.mock import AsyncMock, patch


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
                    self.assertEqual(len(applications), 3)
                    self.assertEqual({row.candidate_id for row in applications}, {ids[0]})
                    self.assertEqual({row.job_id for row in applications}, {job_ids[0], job_ids[1], external})
                    self.assertEqual(applications[0].source, 'automatic')
                    self.assertTrue(all(row.match_score >= 70 for row in applications))
                    external_application = next(row for row in applications if row.job_id == external)
                    self.assertEqual(external_application.status, 'requires_manual')
                    self.assertEqual(external_application.delivery_status, 'requires_manual')
                    runs = list((await db.scalars(select(AutomationRun).where(AutomationRun.candidate_id.in_(ids)))).all())
                    self.assertEqual(len(runs), 4)
                    self.assertEqual({run.candidate_id for run in runs}, {ids[0], ids[4]})
                    self.assertTrue(all(run.status == 'complete' and run.finished_at for run in runs))
                    events = list((await db.scalars(select(AutomationEvent).where(AutomationEvent.run_id.in_([run.id for run in runs])))).all())
                    self.assertEqual(sum(event.status == 'submitted' for event in events), 2)
                    self.assertEqual(sum(event.status == 'already_applied' for event in events), 3)
                    self.assertEqual(sum(event.status == 'requires_manual' for event in events), 1)
                    self.assertEqual(sum(event.status == 'missing_resume' for event in events), 2)
                    self.assertTrue(all(event.job_id == external for event in events if event.status == 'requires_manual'))
            finally:
                async with sessions.begin() as db:
                    await db.execute(delete(Job).where(Job.id == external))
                    await db.execute(delete(User).where(User.id.in_([owner, *ids])))
                await engine.dispose()
        asyncio.run(scenario())

    def test_complete_catalog_scan_and_explicit_run_consent(self):
        async def scenario():
            from sqlalchemy import delete, select
            from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
            from app.automation_models import AutomationEvent, AutomationRun
            from app.config import settings
            from app.models import Application, Job, User
            from app.passwords import hash_password
            from app.worker import automate

            engine = create_async_engine(settings().database_url)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            owner, candidate = uuid.uuid4(), uuid.uuid4()
            try:
                async with sessions.begin() as db:
                    common = {'name': 'Consent fixture', 'password_hash': hash_password('Fixture-only-password!'), 'privacy_version': '2026-01', 'email_verified': True}
                    db.add(User(id=owner, email=f'{owner}@example.com', role='recruiter', **common))
                    db.add(User(id=candidate, email=f'{candidate}@example.com', role='candidate', is_premium=True,
                        automation_enabled=True, skills=['python'], resume_key=str(candidate),
                        preferences={'titles': [str(owner)], 'automation_max_applications_per_run': 1}, **common))
                    await db.flush()
                    for _ in range(205):
                        db.add(Job(recruiter_id=owner, title=str(owner), company='Pagination fixture',
                            description='An approved fixture vacancy for complete page scanning.', salary_min=1000,
                            salary_max=5000, modality='remote', location='Brasil', keywords=['python'], moderation_status='approved'))
                    cancelled = AutomationRun(candidate_id=candidate, status='queued', consent_granted=False)
                    db.add(cancelled)
                    await db.flush()
                    cancelled_id = cancelled.id
                self.assertEqual(await automate(candidate, True, cancelled_id), 0)
                async with sessions() as db:
                    record = await db.get(AutomationRun, cancelled_id)
                    self.assertEqual(record.status, 'cancelled')
                    self.assertEqual(list((await db.scalars(select(Application).where(Application.candidate_id == candidate))).all()), [])
                with patch('app.worker.deliver_application_mail.delay', side_effect=ConnectionError('Disposable broker unavailable')) as dispatch:
                    self.assertEqual(await automate(candidate, True), 1)
                    dispatch.assert_called_once_with()
                async with sessions() as db:
                    runs = list((await db.scalars(select(AutomationRun).where(AutomationRun.candidate_id == candidate, AutomationRun.status == 'complete'))).all())
                    self.assertEqual(len(runs), 1)
                    self.assertTrue(runs[0].consent_granted)
                    self.assertEqual(runs[0].scanned_jobs, 205)
                    self.assertEqual(runs[0].eligible_jobs, 205)
                    self.assertEqual(runs[0].submitted_applications, 1)
                    self.assertEqual(runs[0].omitted_events, 5)
                    events = list((await db.scalars(select(AutomationEvent).where(AutomationEvent.run_id == runs[0].id))).all())
                    self.assertEqual(len(events), 200)
                    self.assertEqual(sum(event.status == 'submitted' for event in events), 1)
                    self.assertEqual(sum(event.status == 'limit_reached' for event in events), 199)
                    self.assertTrue(all(event.source_name and event.job_url and event.destination_channel for event in events if event.status == 'submitted'))
                    complete_id = runs[0].id
                self.assertEqual(await automate(candidate, True, complete_id), 0)
                async with sessions() as db:
                    complete = await db.get(AutomationRun, complete_id)
                    self.assertEqual(complete.scanned_jobs, 205)
                    self.assertEqual(complete.submitted_applications, 1)
            finally:
                async with sessions.begin() as db:
                    await db.execute(delete(User).where(User.id.in_([owner, candidate])))
                await engine.dispose()
        asyncio.run(scenario())

    def test_brazilian_catalog_fallback_rich_metadata_and_foreign_quarantine(self):
        async def scenario():
            from sqlalchemy import delete, select
            from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
            from app.automation_models import AutomationEvent, AutomationRun
            from app.config import settings
            from app.models import Application, Job, User
            from app.passwords import hash_password
            from app.worker import automate

            cfg = settings()
            engine = create_async_engine(cfg.database_url)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            owner, candidate = uuid.uuid4(), uuid.uuid4()
            high, adjacent, foreign, other_region = [uuid.uuid4() for _ in range(4)]
            try:
                async with sessions.begin() as db:
                    common = {'name': 'Brazil catalog fixture', 'password_hash': hash_password('Fixture-only-password!'),
                        'privacy_version': '2026-01', 'email_verified': True}
                    db.add(User(id=owner, email=f'{owner}@example.com', role='recruiter', **common))
                    db.add(User(id=candidate, email=f'{candidate}@example.com', role='candidate', is_premium=True,
                        automation_enabled=True, skills=['suporte', 'windows', 'redes'], resume_key=str(candidate),
                        preferences={'titles': ['Analista de Suporte N2'], 'keywords': ['suporte', 'tecnologia'],
                            'locations': ['Brasília / DF'], 'modalities': ['onsite'], 'min_salary': 3000}, **common))
                    await db.flush()
                    vacancy = {'recruiter_id': owner, 'company': 'Empresa brasileira de teste',
                        'description': 'Atendimento de suporte de tecnologia, resolução de chamados, requisitos técnicos e benefícios informados pela empresa.',
                        'salary_min': 3500, 'salary_max': 5000, 'modality': 'onsite', 'contract_type': 'clt',
                        'location': 'Brasília / DF', 'city': 'Brasília', 'state': 'DF', 'country': 'BR',
                        'moderation_status': 'approved', 'source_name': 'Gupy', 'contact_email': 'selecao@example.com'}
                    db.add(Job(id=high, title='Analista de Suporte N2', keywords=['suporte', 'windows', 'redes'],
                        source_url='https://example.com/vagas/suporte-n2', **vacancy))
                    db.add(Job(id=adjacent, title='Analista de Service Desk', keywords=['atendimento', 'windows', 'office365'],
                        source_url='https://example.com/vagas/service-desk', **vacancy))
                    db.add(Job(id=foreign, **{**vacancy, 'recruiter_id': None, 'country': 'DE', 'city': 'Munich',
                        'state': None, 'location': 'Munich, Bavaria', 'source_name': 'Arbeitnow'},
                        title='Support Engineer', keywords=['suporte', 'windows', 'redes'],
                        source_url='https://example.com/jobs/munich'))
                    db.add(Job(id=other_region, **{**vacancy, 'city': 'São Paulo', 'state': 'SP', 'location': 'São Paulo / SP'},
                        title='Analista de Suporte N2', keywords=['suporte', 'windows', 'redes'],
                        source_url='https://example.com/vagas/suporte-sp'))
                # An unavailable portal never fabricates a replacement vacancy or
                # poisons a useful existing Brazilian catalogue with a failure card.
                fallback = {'collected_jobs': 0, 'failed_sources': 1, 'search_channels': [{
                    'source_name': 'Gupy', 'query': 'Suporte em Brasília / DF', 'location': 'Brasília / DF',
                    'external_url': 'https://portal.gupy.io/job-search/term=suporte', 'destination_channel': 'portal_search'}]}
                with patch('app.worker.settings', return_value=cfg.model_copy(update={'enable_public_collectors': True})), \
                     patch('app.worker.refresh_job_sources', new=AsyncMock(return_value=fallback)), \
                     patch('app.worker.deliver_application_mail.delay'):
                    self.assertEqual(await automate(candidate, True), 1)
                async with sessions() as db:
                    retired = await db.get(Job, foreign)
                    self.assertFalse(retired.active)
                    run = await db.scalar(select(AutomationRun).where(AutomationRun.candidate_id == candidate))
                    self.assertEqual((run.scanned_jobs, run.possible_match_jobs, run.submitted_applications), (2, 1, 1))
                    self.assertEqual(run.collected_jobs, 0)
                    self.assertEqual(run.search_channels_count, 1)
                    self.assertEqual(run.error_count, 1)
                    events = list((await db.scalars(select(AutomationEvent).where(AutomationEvent.run_id == run.id))).all())
                    self.assertFalse(any(item.status == 'failed' for item in events))
                    self.assertFalse(any(item.job_id == foreign for item in events))
                    self.assertFalse(any(item.job_id == other_region for item in events))
                    possible = next(item for item in events if item.job_id == adjacent)
                    self.assertEqual(possible.status, 'possible_match')
                    self.assertTrue(40 <= possible.match_score < 70)
                    self.assertEqual(possible.city, 'Brasília')
                    self.assertEqual(possible.state, 'DF')
                    self.assertEqual(possible.contact_email, 'selecao@example.com')
                    self.assertEqual(possible.contract_type, 'clt')
                    self.assertIn('resolução de chamados', possible.description)
                    self.assertEqual(float(possible.salary_min), 3500)
                    self.assertEqual(len(possible.match_reasons), len(set(possible.match_reasons)))
                    self.assertNotIn(possible.detail, possible.match_reasons)
                    applications = list((await db.scalars(select(Application).where(Application.candidate_id == candidate))).all())
                    self.assertEqual([item.job_id for item in applications], [high])
            finally:
                async with sessions.begin() as db:
                    await db.execute(delete(Job).where(Job.id == foreign))
                    await db.execute(delete(User).where(User.id.in_([owner, candidate])))
                await engine.dispose()
        asyncio.run(scenario())


class WorkerPresentationTests(unittest.TestCase):
    def test_explanation_reasons_are_unique_without_losing_order(self):
        from app.worker import evaluation_reasons
        reasons = evaluation_reasons({'match_reasons': ['Cargo compatível.', 'Localização compatível.'],
            'missed_reasons': ['  Cargo compatível.  ', 'LOCALIZAÇÃO COMPATÍVEL;', 'Confirme o anúncio.']})
        self.assertEqual(reasons, ['Cargo compatível.', 'Localização compatível.', 'Confirme o anúncio.'])
