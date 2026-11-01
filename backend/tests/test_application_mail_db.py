"""PostgreSQL outbox delivery tests; only the SMTP wire is mocked."""
from unittest.mock import patch
import smtplib
import uuid
import pytest
from app import application_mail as mail


@pytest.mark.skipif(not __import__('os').environ.get('VAGOU_TEST_URL'), reason='Disposable integration stack required')
@pytest.mark.parametrize('smtp_failure', [False, True])
def test_committed_delivery_updates_status_and_preserves_registration_on_failure(smtp_failure, tmp_path):
    import asyncio
    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.config import settings
    from app.models import Application, ApplicationNotification, Job, User
    from app.automation_models import AutomationEvent, AutomationRun

    async def scenario():
        engine = create_async_engine(settings().database_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        candidate_id, job_id, run_id, application_id = [uuid.uuid4() for _ in range(4)]
        cfg = settings().model_copy(update={'storage_dir': tmp_path})
        root = tmp_path
        root.mkdir(parents=True, exist_ok=True)
        resume_path = root / str(candidate_id)
        resume_path.write_bytes(mail._cipher().encrypt(b'%PDF-1.7 transaction fixture'))
        try:
            async with sessions.begin() as db:
                candidate = User(id=candidate_id, name='Mail Fixture', email=f'{candidate_id}@example.com',
                    password_hash='unused-fixture', role='candidate', email_verified=True,
                    is_premium=True, automation_enabled=True, privacy_version='2026-01', resume_key=str(candidate_id), skills=['python'])
                db.add(candidate)
                await db.flush()
                job = Job(id=job_id, recruiter_id=None, title='Python Engineer', company='Fixture',
                    description='An isolated fixture vacancy for transactional application email.',
                    salary_min=5000, salary_max=7000, modality='remote', location='Brasil',
                    keywords=['python'], moderation_status='approved', contact_email='recruiter@example.com',
                    source_url='https://example.com/job/fixture')
                db.add(job)
                run = AutomationRun(id=run_id, candidate_id=candidate_id, status='complete', consent_granted=True,
                                    scanned_jobs=1, submitted_applications=1)
                db.add(run)
                await db.flush()
                application = Application(id=application_id, candidate_id=candidate_id, job_id=job_id,
                    source='automatic', status='requires_manual', match_score=90,
                    destination_channel='email', delivery_status='not_requested')
                db.add(application)
                await db.flush()
                db.add(AutomationEvent(run_id=run_id, job_id=job_id, job_title=job.title,
                    job_url=job.source_url, company=job.company, location=job.location,
                    source_name=job.source_name, match_score=90, match_reasons=['Competências compatíveis.'],
                    destination_channel='email', status='requires_manual',
                    detail='Registro encaminhado à fila transacional.'))
                assert await mail.queue_application_email(db, candidate, job, application, run)
                assert await mail.queue_round_report(db, candidate, run, [{
                    'job_id': str(job_id), 'job_title': job.title, 'company_name': job.company,
                    'status': application.status, 'delivery_status': application.delivery_status,
                    'match_score': 90, 'external_url': job.source_url, 'destination_channel': 'email'}])
            async with sessions() as db:
                pending = list((await db.scalars(select(ApplicationNotification).where(ApplicationNotification.user_id == candidate_id))).all())
                assert len(pending) == 2
                assert all('@' not in item.recipient_encrypted and 'Mail Fixture' not in item.payload_encrypted for item in pending)
            with patch('app.application_mail.settings', return_value=cfg), patch('app.application_mail.email_configured', return_value=True), \
                 patch('app.application_mail.send_transactional_message', side_effect=smtplib.SMTPAuthenticationError(535, b'fixture') if smtp_failure else None) as send:
                result = await mail.process_application_outbox()
            async with sessions() as db:
                saved = await db.get(Application, application_id)
                notifications = list((await db.scalars(select(ApplicationNotification).where(ApplicationNotification.user_id == candidate_id))).all())
                assert saved is not None and len(notifications) == 2
                if smtp_failure:
                    assert result['failed'] == 2 and result['sent'] == 0
                    assert saved.status == 'requires_manual' and saved.delivery_status == 'queued'
                    assert all(n.status == 'pending' and n.attempts == 1 and n.payload_encrypted for n in notifications)
                    report = send.call_args_list[-1].args[0].get_body(preferencelist=('plain',)).get_content()
                    assert 'aceite SMTP ainda não confirmado' in report
                    assert 'E-mail aceito pelo servidor SMTP' not in report
                else:
                    assert result['sent'] == 2 and result['failed'] == 0
                    assert saved.status == 'submitted' and saved.delivery_status == 'sent'
                    assert all(n.status == 'sent' and not n.payload_encrypted and not n.recipient_encrypted for n in notifications)
                    messages = [call.args[0] for call in send.call_args_list]
                    attachments = list(messages[0].iter_attachments())
                    assert len(attachments) == 1
                    assert attachments[0].get_payload(decode=True) == b'%PDF-1.7 transaction fixture'
                    report = messages[1].get_body(preferencelist=('plain',)).get_content()
                    assert 'E-mail aceito pelo servidor SMTP' in report
                    html = messages[1].get_body(preferencelist=('html',)).get_content()
                    assert 'https://example.com/job/fixture' in html and '90%' in html
            # The API exposes the latest delivery outcome without changing the
            # immutable historical event or inventing an ATS acknowledgement.
            import os
            import httpx
            from app.security import token
            async with httpx.AsyncClient(base_url=os.environ['VAGOU_TEST_URL']) as client:
                response = await client.get(f'/v1/automation/runs/{run_id}/events',
                    headers={'Authorization': 'Bearer ' + token(candidate)})
            assert response.status_code == 200, response.text
            report = response.json()
            assert report['run']['applications_submitted'] == 1
            assert report['run']['consent_granted'] is True
            entry = report['items'][0]
            assert entry['delivery_status'] == ('queued' if smtp_failure else 'sent')
            assert entry['external_url'] == job.source_url
            assert entry['company_name'] == 'Fixture' and entry['destination_channel'] == 'email'
            assert entry['status'] == 'requires_manual' and entry['match_score'] == 90
            with patch('app.application_mail.settings', return_value=cfg), patch('app.application_mail.email_configured', return_value=True), patch('app.application_mail.send_transactional_message') as repeated:
                again = await mail.process_application_outbox()
            assert again['sent'] == 0
            repeated.assert_not_called()
        finally:
            async with sessions.begin() as db:
                await db.execute(delete(User).where(User.id == candidate_id))
                await db.execute(delete(Job).where(Job.id == job_id))
            resume_path.unlink(missing_ok=True)
            await engine.dispose()
    asyncio.run(scenario())
