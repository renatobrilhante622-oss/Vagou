"""Encrypted transactional mail for applications and executive round reports.

A queued notification is not an SMTP receipt. Delivery is at least once; a
connection loss after provider acceptance can duplicate a message, so stable
Message-ID and database deduplication identify the same notification on retries.
"""
import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from email_validator import EmailNotValidError, validate_email
from sqlalchemy import case, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.smtp_transport import email_configured, send_transactional_message

logger = logging.getLogger(__name__)


class NotificationCancelled(ValueError):
    """The original authorization or attachment is no longer valid."""


def _cipher():
    return Fernet(settings().data_key.get_secret_value().encode())


def _seal(value) -> str:
    return _cipher().encrypt(json.dumps(value, ensure_ascii=False).encode()).decode()


def _open(value: str):
    return json.loads(_cipher().decrypt(value.encode()).decode())


def _email(value) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return validate_email(value, check_deliverability=False).normalized
    except EmailNotValidError:
        return None


def _text(value, limit=500) -> str:
    return ' '.join(str(value or '').split())[:limit]


def _link(value) -> str:
    if not isinstance(value, str) or len(value) > 4096:
        return ''
    try:
        parsed = urlsplit(value)
        return value if parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password else ''
    except ValueError:
        return ''


def _job_link(job) -> str:
    direct = _link(getattr(job, 'source_url', None))
    if direct:
        return direct
    base = _link(getattr(settings(), 'public_api_url', ''))
    return f'{base.rstrip("/")}/v1/jobs/{job.id}' if base else ''


async def _recruiter_address(db, job) -> str | None:
    from app.models import User
    contact = _email(getattr(job, 'contact_email', None))
    if contact:
        return contact
    if job.recruiter_id:
        recruiter = await db.get(User, job.recruiter_id)
        if recruiter and recruiter.role == 'recruiter' and recruiter.email_verified:
            return _email(recruiter.email)
    return None


async def _queue(db, user_id, run_id, application_id, kind, recipient, payload, dedup_key) -> bool:
    from app.models import ApplicationNotification
    statement = insert(ApplicationNotification).values(
        id=uuid.uuid4(), user_id=user_id, run_id=run_id,
        application_id=application_id, kind=kind,
        recipient_encrypted=_seal(recipient), payload_encrypted=_seal(payload),
        status='pending', attempts=0, next_attempt_at=datetime.now(timezone.utc),
        dedup_key=dedup_key,
    ).on_conflict_do_nothing(index_elements=['dedup_key'])
    await db.execute(statement)
    return True


async def queue_application_email(db, user, job, application, run) -> bool:
    """Persist mail intent in the same transaction as the application, no SMTP."""
    recipient = await _recruiter_address(db, job)
    if not recipient or not user.email_verified or not user.automation_enabled or not getattr(run, 'consent_granted', False):
        return False
    phone = ''
    if user.phone_encrypted:
        try:
            phone = _cipher().decrypt(user.phone_encrypted.encode()).decode()
        except Exception:
            logger.warning('application_phone_unavailable error_type=decryption')
    payload = {
        'candidate_name': _text(user.name, 120), 'candidate_email': _email(user.email),
        'candidate_phone': _text(phone, 40), 'skills': [_text(s, 80) for s in (user.skills or [])[:100]],
        'job_title': _text(job.title, 160), 'company_name': _text(job.company, 160),
        'location': _text(job.location, 160), 'external_url': _job_link(job),
        'source_name': _text(job.source_name, 120), 'match_score': application.match_score,
    }
    await _queue(db, user.id, run.id, application.id, 'recruiter_submission', recipient,
                 payload, f'application:{application.id}:recruiter')
    application.delivery_status = 'queued'
    return True


def _entry(entry: dict) -> dict:
    original_link = entry.get('external_url') or entry.get('job_url')
    if isinstance(original_link, str) and original_link.startswith('/v1/jobs/'):
        base = _link(getattr(settings(), 'public_api_url', ''))
        original_link = base.rstrip('/') + original_link if base else ''
    reasons = entry.get('match_reasons') or []
    return {
        'job_id': _text(entry.get('job_id'), 36),
        'description': _text(entry.get('description'), 1500),
        'contact_email': _email(entry.get('contact_email') or entry.get('recruiter_email')),
        'job_title': _text(entry.get('job_title') or entry.get('title'), 160),
        'company_name': _text(entry.get('company_name') or entry.get('company'), 160),
        'location': _text(entry.get('location'), 160), 'source_name': _text(entry.get('source_name'), 120),
        'external_url': _link(original_link),
        'match_score': entry.get('match_score') if isinstance(entry.get('match_score'), (int, float)) else None,
        'match_reasons': [_text(reason, 500) for reason in reasons[:20]] if isinstance(reasons, list) else [],
        'status': _text(entry.get('status'), 24),
        'destination_channel': _text(entry.get('destination_channel'), 120),
        'delivery_status': _text(entry.get('delivery_status'), 24),
    }


async def queue_round_report(db, user, run, entries: list[dict]) -> bool:
    recipient = _email(user.email)
    if not recipient or not user.email_verified or not user.automation_enabled or not getattr(run, 'consent_granted', False):
        return False
    normalized = [_entry(entry) for entry in entries]
    normalized.sort(key=lambda row: 2 if row['status'] == 'search_channel' else 1 if row['status'] == 'possible_match' else 0)
    payload = {'candidate_name': _text(user.name, 120), 'run_id': str(run.id),
               'registered_applications': int(run.submitted_applications or 0),
               'scanned_jobs': int(run.scanned_jobs or 0),
               'entries': normalized[:200], 'omitted_entries': max(0, len(normalized) - 200)}
    return await _queue(db, user.id, run.id, None, 'candidate_report', recipient,
                        payload, f'round:{run.id}:candidate')


def recruiter_message(recipient: str, payload: dict, resume: bytes) -> EmailMessage:
    message = EmailMessage()
    message['From'] = settings().smtp_from
    message['To'] = recipient
    message['Subject'] = f'Candidatura: {_text(payload.get("job_title"), 160)} — Vagou!'
    reply = _email(payload.get('candidate_email'))
    if reply:
        message['Reply-To'] = reply
    body = [
        'Notificação transacional de candidatura — Vagou!',
        f'Vaga: {payload.get("job_title", "")}', f'Empresa: {payload.get("company_name", "")}',
        f'Candidato: {payload.get("candidate_name", "")}', f'E-mail: {payload.get("candidate_email", "")}',
        f'Telefone: {payload.get("candidate_phone", "")}',
        f'Competências declaradas: {", ".join(payload.get("skills", []))}',
        f'Compatibilidade calculada: {payload.get("match_score", 0)}%',
        'O currículo atual está anexado em PDF. Os dados foram compartilhados mediante autorização do candidato.',
        'Este e-mail não comprova recebimento de uma candidatura por um ATS externo.',
    ]
    link = _link(payload.get('external_url'))
    if link:
        body.append('Anúncio oficial: ' + link)
    message.set_content('\n\n'.join(body))
    message.add_attachment(resume, maintype='application', subtype='pdf', filename='curriculo.pdf')
    return message


STATUS_LABELS = {
    'submitted': 'Candidatura registrada no Vagou!', 'already_applied': 'Candidatura já existente',
    'requires_manual': 'Requer conclusão no portal oficial', 'possible_match': 'Possível match: avalie individualmente',
    'search_channel': 'Canal de pesquisa: não representa uma vaga individual',
    'filtered': 'Fora dos critérios', 'failed': 'Não concluída',
}
DELIVERY_LABELS = {
    'queued': 'E-mail agendado; aceite SMTP ainda não confirmado', 'sent': 'E-mail aceito pelo servidor SMTP',
    'failed': 'Falha de envio do e-mail', 'cancelled': 'Envio cancelado',
    'not_requested': 'Sem envio SMTP solicitado', 'requires_manual': 'Candidatura manual necessária',
}


def round_report_message(recipient: str, payload: dict) -> EmailMessage:
    message = EmailMessage()
    message['From'] = settings().smtp_from
    message['To'] = recipient
    message['Subject'] = 'Vagou! — Relatório Executivo da Rodada'
    introduction = (f'Olá, {_text(payload.get("candidate_name"), 120)}.\n'
        f'Vagas reais analisadas: {int(payload.get("scanned_jobs", 0))}.\n'
        f'Candidaturas registradas: {int(payload.get("registered_applications", 0))}.\n'
        'Registro na plataforma, agendamento de e-mail e aceite pelo SMTP são etapas diferentes. '
        'Aceite SMTP não comprova leitura nem inscrição em um portal externo.')
    omitted = int(payload.get('omitted_entries', 0))
    if omitted:
        introduction += f'\nEste relatório resume até 200 itens; {omitted} registros adicionais estão representados nos totais da rodada.'
    plain = [introduction]
    html = ['<html><body><h1>Relatório Executivo da Rodada</h1><p>' + escape(introduction).replace('\n', '<br>') + '</p>']
    for original in payload.get('entries', []):
        row = _entry(original)
        title = row['job_title'] or row['source_name'] or 'Oportunidade'
        status = STATUS_LABELS.get(row['status'], 'Consulte o status no aplicativo')
        delivery = DELIVERY_LABELS.get(row['delivery_status'], 'Consulte a situação de envio no aplicativo')
        score = f"{row['match_score']}%" if row['match_score'] is not None else 'Não se aplica a link de busca'
        details = [title, row['company_name'], row['location'], row['source_name'],
                   'Compatibilidade: ' + score, status, delivery,
                   'Canal: ' + row['destination_channel'], '; '.join(row['match_reasons']),
                   row['description'], 'Contato de recrutamento: ' + row['contact_email'] if row['contact_email'] else '']
        if row['external_url']:
            details.append(row['external_url'])
        plain.append('\n'.join(value for value in details if value))
        display_details = details[:-1] if row['external_url'] else details
        html.append('<section><h2>' + escape(title) + '</h2><ul>' + ''.join(
            '<li>' + escape(value) + '</li>' for value in display_details if value
        ) + '</ul>')
        if row['external_url']:
            html.append('<p><a href="' + escape(row['external_url'], quote=True) + '">Abrir anúncio ou canal oficial</a></p>')
        html.append('</section>')
    html.append('</body></html>')
    message.set_content('\n\n'.join(plain))
    message.add_alternative(''.join(html), subtype='html')
    return message


def _read_private_resume(user) -> bytes:
    cfg = settings()
    if not user.resume_key:
        raise NotificationCancelled('Resume unavailable')
    root = Path(cfg.storage_dir).resolve()
    path = (root / user.resume_key).resolve()
    if not path.is_relative_to(root):
        raise NotificationCancelled('Resume unavailable')
    try:
        with path.open('rb') as stream:
            encrypted = stream.read((cfg.max_pdf_bytes + 128) * 2 + 1)
        if len(encrypted) > (cfg.max_pdf_bytes + 128) * 2:
            raise NotificationCancelled('Resume exceeds limit')
        data = _cipher().decrypt(encrypted)
    except NotificationCancelled:
        raise
    except Exception:
        raise NotificationCancelled('Resume unavailable') from None
    if len(data) > cfg.max_pdf_bytes or not data.startswith(b'%PDF-'):
        raise NotificationCancelled('Resume unavailable')
    return data


async def process_application_outbox(batch_size: int = 50) -> dict:
    from app.models import Application, ApplicationNotification, Job, User
    from app.premium import has_premium_access
    from app.automation_models import AutomationRun
    if not email_configured():
        return {'sent': 0, 'failed': 0, 'cancelled': 0, 'configured': False}
    engine = create_async_engine(settings().database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    counts = {'sent': 0, 'failed': 0, 'cancelled': 0, 'configured': True}
    try:
        async with sessions() as db:
            due = list((await db.execute(select(ApplicationNotification.id, ApplicationNotification.user_id)
                .where(ApplicationNotification.status == 'pending', ApplicationNotification.next_attempt_at <= datetime.now(timezone.utc))
                .order_by(ApplicationNotification.created_at, case((ApplicationNotification.kind == 'recruiter_submission', 0), else_=1), ApplicationNotification.id).limit(max(1, min(batch_size, 100))))).all())
        for notification_id, user_id in due:
            outcome = None
            async with sessions.begin() as db:
                user = await db.scalar(select(User).where(User.id == user_id).with_for_update(skip_locked=True))
                if not user:
                    continue
                item = await db.get(ApplicationNotification, notification_id, with_for_update=True)
                if not item or item.status != 'pending' or item.next_attempt_at > datetime.now(timezone.utc):
                    continue
                application = await db.get(Application, item.application_id) if item.application_id else None
                item.attempts += 1
                try:
                    run = await db.get(AutomationRun, item.run_id)
                    if not run or run.candidate_id != user.id or not run.consent_granted:
                        raise NotificationCancelled('Round authorization unavailable')
                    if not user.email_verified or not user.automation_enabled or not has_premium_access(user):
                        raise NotificationCancelled('Authorization no longer active')
                    recipient = _email(_open(item.recipient_encrypted))
                    payload = _open(item.payload_encrypted)
                    if not recipient or not isinstance(payload, dict):
                        raise NotificationCancelled('Notification invalid')
                    if item.kind == 'recruiter_submission':
                        if not application or application.candidate_id != user.id:
                            raise NotificationCancelled('Application unavailable')
                        job = await db.get(Job, application.job_id)
                        if not job or not job.active or job.moderation_status != 'approved' or recipient != await _recruiter_address(db, job):
                            raise NotificationCancelled('Recruitment channel unavailable')
                        resume = await asyncio.to_thread(_read_private_resume, user)
                        message = recruiter_message(recipient, payload, resume)
                    elif item.kind == 'candidate_report':
                        if recipient != _email(user.email):
                            raise NotificationCancelled('Recipient changed')
                        # Resolve current per-application channel status for the report.
                        wanted = []
                        for row in payload.get('entries', []):
                            try:
                                wanted.append(uuid.UUID(row.get('job_id', '')))
                            except (ValueError, TypeError, AttributeError):
                                pass
                        states = {}
                        for start in range(0, len(wanted), 200):
                            rows = await db.execute(select(Application.job_id, Application.status, Application.delivery_status)
                                .where(Application.candidate_id == user.id, Application.job_id.in_(wanted[start:start + 200])))
                            states.update({str(job_id): (status, delivery) for job_id, status, delivery in rows})
                        for row in payload.get('entries', []):
                            if row.get('job_id') in states:
                                row['status'], row['delivery_status'] = states[row['job_id']]
                        message = round_report_message(recipient, payload)
                    else:
                        raise NotificationCancelled('Notification kind unsupported')
                    identity = hashlib.sha256(item.dedup_key.encode()).hexdigest()
                    message['Message-ID'] = f'<{identity}@notifications.vagou.invalid>'
                    await asyncio.to_thread(send_transactional_message, message)
                except NotificationCancelled:
                    item.status = 'cancelled'
                    item.payload_encrypted = item.recipient_encrypted = ''
                    if application:
                        application.delivery_status = 'cancelled'
                    outcome = 'cancelled'
                    logger.info('application_mail_cancelled notification_id=%s kind=%s', item.id, item.kind)
                except Exception as error:
                    outcome = 'failed'
                    logger.error('application_mail_failed notification_id=%s kind=%s attempt=%s error_type=%s',
                                 item.id, item.kind, item.attempts, type(error).__name__)
                    if item.attempts >= 5:
                        item.status = 'failed'
                        item.payload_encrypted = item.recipient_encrypted = ''
                        if application:
                            application.delivery_status = 'failed'
                    else:
                        item.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=min(30 * 2 ** item.attempts, 1800))
                else:
                    item.status = 'sent'
                    item.delivered_at = datetime.now(timezone.utc)
                    item.payload_encrypted = item.recipient_encrypted = ''
                    if application:
                        application.delivery_status = 'sent'
                        if application.status == 'requires_manual' and application.destination_channel == 'email':
                            application.status = 'submitted'
                    outcome = 'sent'
                    logger.info('application_mail_accepted notification_id=%s kind=%s', item.id, item.kind)
            if outcome:
                counts[outcome] += 1
        return counts
    finally:
        await engine.dispose()
