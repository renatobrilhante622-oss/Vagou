"""Premium matching, truthful delivery reports, feed ingestion and durable mail.

A submitted application is delivered within Vagou! to its owning recruiter.
An external vacancy requires a manual action; opening a link is never counted
as a sent application. Jobs/user preferences are rechecked under database locks.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from celery import Celery
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.automation_models import AutomationEvent, AutomationRun
from app.config import settings
from app.job_sources import FeedError, fetch_feed
from app.matching import eligible, match
from app.models import Job, User
from app.services import apply

celery = Celery('vagou', broker=settings().redis_url)
celery.conf.update(
    task_serializer='json', accept_content=['json'], result_serializer='json',
    task_ignore_result=True, task_acks_late=True, worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        'premium-automation': {'task': 'vagou.automate', 'schedule': 60.0},
        'verification-mail': {'task': 'vagou.deliver_verification_mail', 'schedule': 15.0},
        'authorized-job-feeds': {'task': 'vagou.refresh_job_sources', 'schedule': 900.0},
    },
)


MAX_DETAILED_EVENTS_PER_RUN = 200


def event(db, run, status, detail, job=None):
    logged = getattr(run, '_logged_event_count', 0)
    if logged >= MAX_DETAILED_EVENTS_PER_RUN:
        run.omitted_events += 1
        return
    run._logged_event_count = logged + 1
    db.add(AutomationEvent(run_id=run.id, job_id=job.id if job else None,
        job_title=job.title if job else None,
        job_url=(job.source_url or f'/v1/jobs/{job.id}') if job else None,
        status=status, detail=detail))


async def automate():
    engine = create_async_engine(settings().database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    submitted = 0
    try:
        cursor = None
        while True:
            async with sessions() as db:
                query = select(User.id).where(User.role == 'candidate', User.email_verified.is_(True),
                    User.is_premium.is_(True), User.automation_enabled.is_(True)).order_by(User.id).limit(100)
                if cursor:
                    query = query.where(User.id > cursor)
                ids = list((await db.scalars(query)).all())
            if not ids:
                break
            for user_id in ids:
                try:
                    async with sessions.begin() as db:
                        user = await db.scalar(select(User).where(User.id == user_id).with_for_update(skip_locked=True))
                        if not user or not user.email_verified or not user.is_premium or not user.automation_enabled:
                            continue
                        configured_interval = user.preferences.get('automation_interval_minutes', 60)
                        interval = max(15, min(1440, configured_interval)) if isinstance(configured_interval, int) else 60
                        latest = await db.scalar(select(AutomationRun.started_at).where(AutomationRun.candidate_id == user.id)
                            .order_by(AutomationRun.started_at.desc()).limit(1))
                        if latest and latest > datetime.now(timezone.utc) - timedelta(minutes=interval):
                            continue
                        run = AutomationRun(candidate_id=user.id, scanned_jobs=0, eligible_jobs=0,
                            submitted_applications=0, manual_review_jobs=0, error_count=0, omitted_events=0)
                        db.add(run)
                        await db.flush()
                        if not user.resume_key:
                            event(db, run, 'missing_resume', 'Envie um currículo PDF para ativar os envios automáticos.')
                        else:
                            job_cursor = None
                            configured_limit = settings().automation_max_applications_per_run
                            requested_limit = user.preferences.get('automation_max_applications_per_run', configured_limit)
                            limit = min(configured_limit, requested_limit) if isinstance(requested_limit, int) and requested_limit > 0 else configured_limit
                            while run.submitted_applications < limit:
                                query = select(Job).where(Job.active.is_(True), Job.moderation_status == 'approved').order_by(Job.id).limit(200)
                                if job_cursor:
                                    query = query.where(Job.id > job_cursor)
                                jobs = list((await db.scalars(query)).all())
                                if not jobs:
                                    break
                                for job in jobs:
                                    run.scanned_jobs += 1
                                    if not eligible(job, user.preferences) or match(user.skills, job.keywords)['category'] != 'high':
                                        continue
                                    run.eligible_jobs += 1
                                    if job.recruiter_id is None:
                                        run.manual_review_jobs += 1
                                        event(db, run, 'requires_manual', 'Vaga externa compatível. Confirme a candidatura no canal oficial.', job)
                                        continue
                                    locked = await db.scalar(select(Job).where(Job.id == job.id, Job.active.is_(True),
                                        Job.moderation_status == 'approved').with_for_update())
                                    if not locked:
                                        continue
                                    _, created = await apply(db, user, locked, 'automatic')
                                    if created:
                                        run.submitted_applications += 1
                                        event(db, run, 'submitted', 'Candidatura entregue ao recrutador dentro do Vagou!.', locked)
                                    else:
                                        event(db, run, 'already_applied', 'Esta vaga já possui uma candidatura sua.', locked)
                                    if run.submitted_applications >= limit:
                                        break
                                job_cursor = jobs[-1].id
                        run.status = 'complete'
                        run.finished_at = datetime.now(timezone.utc)
                    # Only publish aggregate counts after the transaction commits.
                    submitted += run.submitted_applications
                except OperationalError:
                    # Transaction rollback preserves application idempotency. A
                    # Celery retry is safe; never record an uncommitted send.
                    raise
                except Exception:
                    async with sessions.begin() as db:
                        user_exists = await db.scalar(select(User.id).where(User.id == user_id))
                        if user_exists:
                            failed = AutomationRun(candidate_id=user_id, status='failed', finished_at=datetime.now(timezone.utc), error_count=1)
                            db.add(failed)
                            await db.flush()
                            event(db, failed, 'failed', 'O ciclo não foi concluído. Uma nova tentativa ocorrerá automaticamente.')
            cursor = ids[-1]
        return submitted
    finally:
        await engine.dispose()


async def refresh_job_sources():
    cfg = settings()
    if not cfg.job_source_urls:
        return {'imported': 0, 'failed_sources': 0, 'configured': False}
    engine = create_async_engine(cfg.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    imported, failed = 0, 0
    try:
        for url in cfg.job_source_urls:
            try:
                jobs = await fetch_feed(url, cfg.job_source_allowed_hosts, cfg.job_source_max_bytes, cfg.job_source_max_jobs)
                source = urlsplit(url).hostname[:120]
                source_imported = 0
                async with sessions.begin() as db:
                    for job in jobs:
                        statement = insert(Job).values(**job.values(), source_name=source, recruiter_id=None,
                            active=True, moderation_status='approved' if cfg.job_source_auto_approve else 'pending')
                        result = await db.execute(statement.on_conflict_do_nothing(index_elements=['source_name', 'source_external_id']).returning(Job.id))
                        source_imported += int(result.scalar_one_or_none() is not None)
                imported += source_imported
            except Exception:
                # No URL query parameters, credentials or source response in logs.
                failed += 1
        return {'imported': imported, 'failed_sources': failed, 'configured': True}
    finally:
        await engine.dispose()


@celery.task(name='vagou.automate', autoretry_for=(ConnectionError, OperationalError), retry_backoff=True, max_retries=3)
def run_automation():
    return asyncio.run(automate())


@celery.task(name='vagou.refresh_job_sources', autoretry_for=(OperationalError,), retry_backoff=True, max_retries=3)
def run_job_sources():
    return asyncio.run(refresh_job_sources())


@celery.task(name='vagou.deliver_verification_mail', autoretry_for=(OperationalError,), retry_backoff=True, max_retries=3)
def deliver_verification_mail():
    from app.mailer import process_email_outbox
    return asyncio.run(process_email_outbox())
