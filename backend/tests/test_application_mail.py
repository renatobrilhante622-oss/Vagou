"""Transactional mail: encrypted intent, safe reports and private PDF boundaries."""
from types import SimpleNamespace
import uuid
from unittest.mock import AsyncMock, patch
from cryptography.fernet import Fernet
import pytest
from app import application_mail as mail


@pytest.fixture
def cfg(tmp_path):
    key = Fernet.generate_key()
    return SimpleNamespace(data_key=SimpleNamespace(get_secret_value=lambda: key.decode()),
        smtp_from='Vagou! <sender@example.com>', storage_dir=tmp_path,
        max_pdf_bytes=1024, public_api_url='https://api.example.com')


def user():
    return SimpleNamespace(id=uuid.uuid4(), email='candidate@example.com', name='Ana Silva',
        email_verified=True, automation_enabled=True, phone_encrypted=None,
        skills=['Python', 'SQL'], resume_key='private-resume')


def test_report_safe_links_and_no_false_delivery_claim(cfg):
    payload = {'candidate_name': 'Ana <Admin>', 'registered_applications': 1, 'scanned_jobs': 3,
        'entries': [
            {'job_title': '<script>unsafe</script>', 'company_name': 'Employer', 'location': 'Recife / PE',
             'external_url': 'https://example.com/jobs/1?x="quoted"', 'source_name': 'Official',
             'match_score': 90, 'match_reasons': ['Python compatível'], 'status': 'submitted',
             'delivery_status': 'queued', 'destination_channel': 'email'},
            {'job_title': 'Analista', 'match_score': 55, 'status': 'possible_match',
             'external_url': 'javascript:alert(1)', 'match_reasons': ['Experiência próxima']},
            {'job_title': 'Pesquisar vagas', 'status': 'search_channel', 'match_score': None},
        ]}
    with patch('app.application_mail.settings', return_value=cfg):
        message = mail.round_report_message('candidate@example.com', payload)
    plain = message.get_body(preferencelist=('plain',)).get_content()
    html = message.get_body(preferencelist=('html',)).get_content()
    assert 'Candidaturas registradas: 1' in plain
    assert 'aceite SMTP ainda não confirmado' in plain
    assert 'Possível match' in plain
    assert 'Não se aplica a link de busca' in plain
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert 'href="https://example.com/jobs/1?x=&quot;quoted&quot;"' in html
    assert 'javascript:' not in html
    assert 'Experiência próxima' in html


def test_recruiter_current_pdf_and_reply_address(cfg):
    payload = {'candidate_name': 'Ana', 'candidate_email': 'candidate@example.com',
               'candidate_phone': '+5511999999999', 'skills': ['python'],
               'job_title': 'Backend\nDeveloper', 'company_name': 'Company', 'match_score': 90}
    with patch('app.application_mail.settings', return_value=cfg):
        message = mail.recruiter_message('recruiter@example.com', payload, b'%PDF-1.7 fixture')
    assert message['Reply-To'] == 'candidate@example.com'
    assert '\n' not in str(message['Subject'])
    attachments = list(message.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_content_type() == 'application/pdf'
    assert attachments[0].get_payload(decode=True) == b'%PDF-1.7 fixture'
    assert 'não comprova recebimento' in message.get_body(preferencelist=('plain',)).get_content()


def test_private_resume_authenticated_and_bounded(cfg):
    candidate = user()
    cipher = Fernet(cfg.data_key.get_secret_value().encode())
    resume = b'%PDF-1.7 fixture'
    (cfg.storage_dir / candidate.resume_key).write_bytes(cipher.encrypt(resume))
    with patch('app.application_mail.settings', return_value=cfg):
        assert mail._read_private_resume(candidate) == resume
        (cfg.storage_dir / candidate.resume_key).write_bytes(cipher.encrypt(b'%PDF-' + b'x' * 1024))
        with pytest.raises(mail.NotificationCancelled):
            mail._read_private_resume(candidate)
        candidate.resume_key = '../outside.pdf'
        with pytest.raises(mail.NotificationCancelled):
            mail._read_private_resume(candidate)


def test_queue_encrypted_and_idempotent_by_application(cfg):
    import asyncio
    candidate = user()
    run = SimpleNamespace(id=uuid.uuid4(), consent_granted=True)
    job = SimpleNamespace(id=uuid.uuid4(), recruiter_id=None, contact_email='recruiter@example.com',
        title='Python', company='Company', location='Recife / PE', source_url='https://example.com/jobs/1', source_name='Partner')
    application = SimpleNamespace(id=uuid.uuid4(), match_score=90, delivery_status='not_requested')
    db = SimpleNamespace(execute=AsyncMock())
    with patch('app.application_mail.settings', return_value=cfg):
        assert asyncio.run(mail.queue_application_email(db, candidate, job, application, run))
        parameters = db.execute.call_args.args[0].compile().params
        assert 'candidate@example.com' not in repr(parameters)
        assert 'recruiter@example.com' not in repr(parameters)
        assert mail._open(parameters['recipient_encrypted']) == 'recruiter@example.com'
        assert mail._open(parameters['payload_encrypted'])['candidate_name'] == candidate.name
        assert str(application.id) in parameters['dedup_key']
        assert 'ON CONFLICT' in str(db.execute.call_args.args[0])
    assert application.delivery_status == 'queued'


def test_missing_contact_does_not_invent_destination(cfg):
    import asyncio
    candidate = user()
    job = SimpleNamespace(recruiter_id=None, contact_email=None)
    db = SimpleNamespace(execute=AsyncMock())
    with patch('app.application_mail.settings', return_value=cfg):
        assert not asyncio.run(mail.queue_application_email(db, candidate, job,
            SimpleNamespace(), SimpleNamespace()))
    db.execute.assert_not_awaited()


def test_revoked_round_consent_does_not_queue_email_or_report(cfg):
    import asyncio
    candidate = user()
    job = SimpleNamespace(recruiter_id=None, contact_email='recruiter@example.com')
    run = SimpleNamespace(consent_granted=False)
    db = SimpleNamespace(execute=AsyncMock())
    with patch('app.application_mail.settings', return_value=cfg):
        assert not asyncio.run(mail.queue_application_email(db, candidate, job, SimpleNamespace(), run))
        assert not asyncio.run(mail.queue_round_report(db, candidate, run, []))
    db.execute.assert_not_awaited()


def test_internal_report_links_use_public_api_url(cfg):
    with patch('app.application_mail.settings', return_value=cfg):
        row = mail._entry({'external_url': '/v1/jobs/fixture', 'job_title': 'Python'})
    assert row['external_url'] == 'https://api.example.com/v1/jobs/fixture'
    cfg.public_api_url = 'javascript:alert(1)'
    with patch('app.application_mail.settings', return_value=cfg):
        assert not mail._entry({'external_url': '/v1/jobs/fixture'})['external_url']


def test_unconfigured_mail_does_not_create_smtp_success():
    import asyncio
    with patch('app.application_mail.email_configured', return_value=False):
        result = asyncio.run(mail.process_application_outbox())
    assert result == {'sent': 0, 'failed': 0, 'cancelled': 0, 'configured': False}
