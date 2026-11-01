"""Premium matching, truthful delivery reports, feed ingestion and durable mail.

A submitted application is delivered within Vagou! to its owning recruiter.
External registrations require SMTP acceptance or a manual portal action;
opening a link never counts as delivery. Preferences are rechecked under locks.
"""
import asyncio
import logging
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from uuid import UUID

from celery import Celery
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.automation_models import AutomationEvent, AutomationRun
from app.config import settings
from app.collectors import collect_authorized_sources
from app.matching import compatible_region, dedupe_reasons, evaluate_job, is_brazilian_job, job_location_details
from app.models import Application, Job, User
from app.premium import has_premium_access, premium_test_emails
from app.services import apply
from app.job_sources import clean_description

celery = Celery('vagou', broker=settings().redis_url, backend=settings().redis_url)
celery.conf.update(
    task_serializer='json', accept_content=['json'], result_serializer='json',
    task_ignore_result=False, task_acks_late=True, worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        'premium-automation': {'task': 'vagou.automate', 'schedule': 60.0},
        'verification-mail': {'task': 'vagou.deliver_verification_mail', 'schedule': 15.0},
        'authorized-job-feeds': {'task': 'vagou.refresh_job_sources', 'schedule': 900.0},
        'application-mail': {'task': 'vagou.deliver_application_mail', 'schedule': 15.0},
        'system-mail': {'task': 'vagou.deliver_system_mail', 'schedule': 15.0},
    },
)


logger = logging.getLogger(__name__)

MAX_DETAILED_EVENTS_PER_RUN = 200


def evaluation_reasons(evaluation):
    """Keep one readable occurrence of each explainable matching reason."""
    return dedupe_reasons(evaluation.get('match_reasons', []) + evaluation.get('missed_reasons', []))


def vacancy_snapshot(job):
    """Public vacancy facts only; unknown values remain explicitly unknown."""
    geography = job_location_details(job)
    return {'description': clean_description(job.description, 3000),
            'contact_email': job.contact_email, 'city': geography.get('city'),
            'state': geography.get('state'), 'modality': job.modality,
            'contract_type': job.contract_type,
            'salary_min': float(job.salary_min) if job.salary_min is not None else None,
            'salary_max': float(job.salary_max) if job.salary_max is not None else None}


def event(db, run, status, detail, job=None, evaluation=None, *, destination_channel=None, search_channel=None):
    logged = getattr(run, '_logged_event_count', 0)
    if logged >= MAX_DETAILED_EVENTS_PER_RUN:
        run.omitted_events += 1
        return
    run._logged_event_count = logged + 1
    db.add(AutomationEvent(run_id=run.id, job_id=job.id if job else None,
        job_title=job.title if job else (search_channel.get('query') if search_channel else None),
        job_url=(job.source_url or f'/v1/jobs/{job.id}') if job else (search_channel.get('external_url') if search_channel else None),
        company=job.company if job else None, location=job.location if job else (search_channel.get('location') if search_channel else None),
        source_name=job.source_name if job else (search_channel.get('source_name') if search_channel else None),
        match_score=evaluation['match_score'] if evaluation else None,
        match_reasons=evaluation_reasons(evaluation) if evaluation else None,
        destination_channel=destination_channel or (search_channel.get('destination_channel') if search_channel else None),
        status=status, detail=detail[:255], **(vacancy_snapshot(job) if job else {})))


def report_entry(job, evaluation, status, destination_channel, delivery_status=None):
    return {'job_id': str(job.id), 'job_title': job.title, 'company_name': job.company,
            'location': job.location, 'source_name': job.source_name,
            'external_url': job.source_url or f'/v1/jobs/{job.id}',
            'match_score': evaluation['match_score'],
            'match_reasons': evaluation_reasons(evaluation),
            'status': status, 'destination_channel': destination_channel,
            'delivery_status': delivery_status, **vacancy_snapshot(job)}


async def automate(candidate_id=None, force=False, run_id=None, progress=None):
    candidate_id = UUID(str(candidate_id)) if candidate_id else None
    run_id = UUID(str(run_id)) if run_id else None
    if (force or run_id) and candidate_id is None:
        raise ValueError('A requested cycle must target one candidate')
    from app.job_catalog import quarantine_non_brazilian_jobs
    await quarantine_non_brazilian_jobs()
    engine = create_async_engine(settings().database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    submitted = 0
    try:
        allowed_test_emails = premium_test_emails()
        cursor = None
        while True:
            async with sessions() as db:
                query = select(User.id).where(User.role.in_(['candidate','super_admin','moderator']), User.is_active.is_(True), User.email_verified.is_(True),
                    User.automation_enabled.is_(True)).order_by(User.id).limit(100)
                query = query.where(or_(User.is_premium.is_(True), func.lower(User.email).in_(allowed_test_emails))) if allowed_test_emails else query.where(User.is_premium.is_(True))
                if candidate_id:
                    query = query.where(User.id == candidate_id)
                if cursor:
                    query = query.where(User.id > cursor)
                ids = list((await db.scalars(query)).all())
                if not ids:
                    break
            for user_id in ids:
                collected_jobs = failed_sources = 0
                search_channels = []
                if settings().enable_public_collectors:
                    async with sessions() as db:
                        snapshot = await db.get(User, user_id)
                        search_preferences = (snapshot.preferences or {}) if snapshot else {}
                        interval_minutes = search_preferences.get('automation_interval_minutes', 60)
                        interval_minutes = max(15, min(1440, interval_minutes)) if isinstance(interval_minutes, int) else 60
                        latest_run = await db.scalar(select(AutomationRun.started_at).where(AutomationRun.candidate_id == user_id)
                            .order_by(AutomationRun.started_at.desc()).limit(1))
                        due = force or not latest_run or latest_run <= datetime.now(timezone.utc) - timedelta(minutes=interval_minutes)
                    if due:
                        try:
                            collection = await refresh_job_sources(search_preferences)
                            collected_jobs = collection['collected_jobs']
                            failed_sources = collection['failed_sources']
                            search_channels = collection.get('search_channels', [])
                        except Exception as error:
                            logger.error('automation_source_collection_failed error_type=%s', type(error).__name__)
                            failed_sources = 1
                try:
                    async with sessions.begin() as db:
                        user = await db.scalar(select(User).where(User.id == user_id).with_for_update(skip_locked=True))
                        if not user:
                            continue
                        if not user.is_active or not user.email_verified or not has_premium_access(user) or not user.automation_enabled:
                            if run_id:
                                cancelled = await db.get(AutomationRun, run_id)
                                if cancelled and cancelled.candidate_id == user.id:
                                    cancelled.status = 'cancelled'
                                    cancelled.finished_at = datetime.now(timezone.utc)
                                    event(db, cancelled, 'failed', 'Execução cancelada porque a autorização de automação foi desativada.')
                            continue
                        preferences = user.preferences or {}
                        configured_interval = preferences.get('automation_interval_minutes', 60)
                        interval = max(15, min(1440, configured_interval)) if isinstance(configured_interval, int) else 60
                        latest = await db.scalar(select(AutomationRun.started_at).where(AutomationRun.candidate_id == user.id)
                            .order_by(AutomationRun.started_at.desc()).limit(1))
                        if not force and latest and latest > datetime.now(timezone.utc) - timedelta(minutes=interval):
                            continue
                        run = await db.get(AutomationRun, run_id) if run_id else None
                        if run is not None and run.candidate_id != user.id:
                            raise ValueError('Run does not belong to candidate')
                        if run is not None and run.status in {'complete', 'failed', 'cancelled'}:
                            continue
                        if run is None:
                            run = AutomationRun(candidate_id=user.id, collected_jobs=collected_jobs,
                                scanned_jobs=0, external_jobs_scanned=0,
                                filtered_jobs=0, possible_match_jobs=0, eligible_jobs=0,
                                submitted_applications=0, manual_review_jobs=0,
                                error_count=0, omitted_events=0, consent_granted=True,
                                search_channels_count=len(search_channels))
                            db.add(run)
                            await db.flush()
                        else:
                            run.collected_jobs = collected_jobs
                            run.search_channels_count = len(search_channels)
                        if not run.consent_granted:
                            run.status = 'cancelled'
                            run.finished_at = datetime.now(timezone.utc)
                            event(db, run, 'failed', 'Execução cancelada: consentimento para candidaturas não concedido.')
                            continue
                        entries = []
                        for channel in search_channels:
                            event(db, run, 'search_channel',
                                'Canal de pesquisa regional; abra para consultar vagas reais atualizadas. Não é uma vaga nem uma candidatura.',
                                search_channel=channel, destination_channel='portal_search')
                            entries.append({**channel, 'status': 'search_channel', 'job_title': channel.get('query'),
                                'match_score': None, 'match_reasons': [], 'company_name': None})
                        if failed_sources:
                            run.error_count += failed_sources
                            logger.info('automation_sources_degraded count=%s fallback=verified_brazilian_catalog', failed_sources)
                        run.status = 'running'
                        if not user.resume_key:
                            event(db, run, 'missing_resume', 'Envie um currículo PDF para ativar os envios automáticos.')
                        else:
                            from app.mailer import queue_application_email
                            job_cursor = None
                            configured_limit = settings().automation_max_applications_per_run
                            requested_limit = preferences.get('automation_max_applications_per_run', configured_limit)
                            limit = min(configured_limit, requested_limit) if isinstance(requested_limit, int) and requested_limit > 0 else configured_limit
                            while True:
                                query = select(Job).where(Job.active.is_(True), Job.moderation_status == 'approved').order_by(Job.id).limit(200)
                                if job_cursor:
                                    query = query.where(Job.id > job_cursor)
                                jobs = list((await db.scalars(query)).all())
                                if not jobs:
                                    break
                                applied_ids = set((await db.scalars(select(Application.job_id).where(
                                    Application.candidate_id == user.id, Application.job_id.in_([job.id for job in jobs])))).all())
                                for job in jobs:
                                    if not is_brazilian_job(job) or not compatible_region(job, preferences):
                                        # Unknown/foreign scope is never counted as a
                                        # Brazilian vacancy or allowed to auto-submit.
                                        continue
                                    run.scanned_jobs += 1
                                    if job.recruiter_id is None:
                                        run.external_jobs_scanned += 1
                                    evaluation = evaluate_job(job, user.skills, preferences)
                                    score = evaluation['match_score']
                                    if score < 40:
                                        run.filtered_jobs += 1
                                        event(db, run, 'filtered', 'Vaga fora dos critérios desta rodada.', job, evaluation)
                                    elif score < 70:
                                        run.possible_match_jobs += 1
                                        event(db, run, 'possible_match', 'Oportunidade próxima ao seu perfil para avaliação individual.', job, evaluation)
                                        entries.append(report_entry(job, evaluation, 'possible_match', 'candidate_review'))
                                    else:
                                        run.eligible_jobs += 1
                                        if job.id in applied_ids:
                                            event(db, run, 'already_applied', 'Esta vaga já possui uma candidatura sua.', job, evaluation)
                                            entries.append(report_entry(job, evaluation, 'already_applied', 'existing_application'))
                                        elif run.submitted_applications >= limit:
                                            event(db, run, 'limit_reached', 'Vaga compatível adiada: o limite de registros deste ciclo foi atingido.', job, evaluation)
                                            entries.append(report_entry(job, evaluation, 'limit_reached', 'candidate_review'))
                                        else:
                                            locked = await db.scalar(select(Job).where(Job.id == job.id, Job.active.is_(True),
                                                Job.moderation_status == 'approved').with_for_update())
                                            if locked:
                                                status = 'submitted' if locked.recruiter_id else 'requires_manual'
                                                application_id, created = await apply(db, user, locked, 'automatic', score=score, status=status)
                                                if created:
                                                    application = await db.get(Application, application_id)
                                                    internal = locked.recruiter_id is not None
                                                    application.destination_channel = 'platform' if internal else 'portal_link'
                                                    application.delivery_status = 'not_requested' if internal else 'requires_manual'
                                                    queued = await queue_application_email(db, user, locked, application, run)
                                                    if queued and not internal:
                                                        application.destination_channel = 'email'
                                                    run.submitted_applications += 1
                                                    if not internal and not queued:
                                                        run.manual_review_jobs += 1
                                                    event_status = 'submitted' if internal else 'requires_manual'
                                                    detail = ('Candidatura registrada e entregue ao recrutador no Vagou!.' if internal else
                                                        'Candidatura registrada; encaminhamento SMTP em fila, ainda sem confirmação de entrega.' if queued else
                                                        'Candidatura registrada; conclua no portal oficial, que não oferece canal de envio integrado.')
                                                    event(db, run, event_status, detail, locked, evaluation,
                                                        destination_channel=application.destination_channel)
                                                    entries.append(report_entry(locked, evaluation, event_status,
                                                        application.destination_channel, application.delivery_status))
                                                else:
                                                    event(db, run, 'already_applied', 'Esta vaga já possui uma candidatura sua.', locked, evaluation)
                                    if progress and run.scanned_jobs % 20 == 0:
                                        progress({'scanned_jobs': run.scanned_jobs, 'external_jobs_scanned': run.external_jobs_scanned,
                                            'filtered_jobs': run.filtered_jobs, 'possible_match_jobs': run.possible_match_jobs,
                                            'eligible_jobs': run.eligible_jobs, 'submitted_applications': run.submitted_applications,
                                            'manual_review_jobs': run.manual_review_jobs, 'search_channels_count': run.search_channels_count})
                                job_cursor = jobs[-1].id
                                if progress:
                                    progress({'scanned_jobs': run.scanned_jobs, 'external_jobs_scanned': run.external_jobs_scanned,
                                        'filtered_jobs': run.filtered_jobs, 'possible_match_jobs': run.possible_match_jobs,
                                        'eligible_jobs': run.eligible_jobs, 'submitted_applications': run.submitted_applications,
                                        'manual_review_jobs': run.manual_review_jobs, 'search_channels_count': run.search_channels_count})
                        from app.mailer import queue_execution_report
                        await queue_execution_report(db, user, run, entries)
                        run.status = 'complete'
                        run.finished_at = datetime.now(timezone.utc)
                    # Only enqueue delivery after commit. SMTP runs in its own task;
                    # cancelling an inline to_thread call could resend accepted mail.
                    submitted += run.submitted_applications
                    try:
                        deliver_application_mail.delay()
                    except Exception as error:
                        # The periodic outbox task retries committed messages even
                        # when immediate broker publishing is unavailable.
                        logger.error('application_mail_dispatch_deferred error_type=%s', type(error).__name__)
                except OperationalError:
                    raise
                except Exception as error:
                    logger.error('automation_cycle_failed error_type=%s', type(error).__name__)
                    async with sessions.begin() as db:
                        user_exists = await db.scalar(select(User.id).where(User.id == user_id))
                        if user_exists:
                            failed = await db.get(AutomationRun, run_id) if run_id else None
                            if failed is None:
                                failed = AutomationRun(candidate_id=user_id, consent_granted=True)
                                db.add(failed)
                            if failed.candidate_id != user_id:
                                continue
                            failed.status = 'failed'
                            failed.finished_at = datetime.now(timezone.utc)
                            failed.error_count = 1
                            await db.flush()
                            event(db, failed, 'failed', 'O ciclo não foi concluído. Uma nova tentativa ocorrerá automaticamente.')
            cursor = ids[-1]
        if candidate_id and run_id:
            async with sessions.begin() as db:
                queued = await db.get(AutomationRun, run_id)
                if queued and queued.candidate_id == candidate_id and queued.status == 'queued':
                    queued.status = 'cancelled'
                    queued.finished_at = datetime.now(timezone.utc)
                    event(db, queued, 'failed', 'Execução cancelada porque a conta não está mais autorizada para automação.')
        return submitted
    finally:
        await engine.dispose()


async def refresh_job_sources(preferences: dict | None = None):
    cfg = settings()
    from app.job_catalog import quarantine_non_brazilian_jobs
    archived = await quarantine_non_brazilian_jobs()
    if not cfg.enable_public_collectors:
        return {'imported': 0, 'collected_jobs': 0, 'failed_sources': 0,
            'configured': False, 'enabled': False, 'archived_jobs': archived}
    has_search_query = bool(preferences and any(preferences.get(key) for key in ('titles', 'keywords', 'locations', 'modalities', 'contract_types', 'min_salary')))
    if not cfg.job_source_urls and not has_search_query:
        return {'imported': 0, 'collected_jobs': 0, 'failed_sources': 0,
            'configured': False, 'enabled': True}
    engine = create_async_engine(cfg.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    imported = collected = 0
    search_channels = []
    try:
        sources, failed = await collect_authorized_sources(cfg.job_source_urls,
            cfg.job_source_allowed_hosts, cfg.job_source_max_bytes, cfg.job_source_max_jobs,
            preferences=preferences)
        source_health = {}
        for source in sources:
            source_health.update(getattr(source, 'health', {}))
            search_channels.extend(asdict(channel) for channel in getattr(source, 'search_channels', []))
            async with sessions.begin() as db:
                for job in source.jobs:
                    if not is_brazilian_job(job):
                        continue
                    collected += 1
                    values = {**job.values(), 'source_name': source.name, 'recruiter_id': None,
                        'active': True, 'moderation_status': 'approved' if source.auto_approve or cfg.job_source_auto_approve else 'pending'}
                    statement = insert(Job).values(**values)
                    updates = {key: getattr(statement.excluded, key) for key in (
                        'title', 'company', 'description', 'location', 'modality', 'contract_type',
                        'keywords', 'salary_min', 'salary_max', 'source_url', 'contact_email',
                        'city', 'state', 'country', 'expires_at')}
                    result = await db.execute(statement.on_conflict_do_update(
                        index_elements=['source_name', 'source_external_id'], set_=updates).returning(Job.id))
                    imported += int(result.scalar_one_or_none() is not None)
        return {'imported': imported, 'collected_jobs': collected, 'failed_sources': failed,
            'configured': True, 'search_channels': search_channels, 'archived_jobs': archived, 'source_health': source_health}
    finally:
        await engine.dispose()


@celery.task(bind=True, name='vagou.automate', autoretry_for=(ConnectionError, OperationalError), retry_backoff=True, max_retries=3)
def run_automation(self, candidate_id=None, force=False, run_id=None):
    def publish_progress(progress):
        self.update_state(state='PROGRESS', meta=progress)
    return asyncio.run(automate(candidate_id, force, run_id, publish_progress))


@celery.task(name='vagou.refresh_job_sources', autoretry_for=(OperationalError,), retry_backoff=True, max_retries=3)
def run_job_sources():
    return asyncio.run(refresh_job_sources())


@celery.task(name='vagou.deliver_verification_mail', autoretry_for=(OperationalError,), retry_backoff=True, max_retries=3)
def deliver_verification_mail():
    from app.mailer import process_email_outbox
    return asyncio.run(process_email_outbox())


@celery.task(name='vagou.deliver_application_mail', autoretry_for=(OperationalError,), retry_backoff=True, max_retries=3)
def deliver_application_mail():
    from app.mailer import process_application_outbox
    return asyncio.run(process_application_outbox())


@celery.task(name='vagou.deliver_system_mail')
def deliver_system_mail():
    from app.system_mail import process_notices
    return asyncio.run(process_notices())


@celery.task(name='vagou.sync_admin_sources')
def sync_admin_sources(actor_id):
    async def execute():
        from app.collectors import _source_cache
        from app.models import AdminAudit
        _source_cache.clear()
        result=await refresh_job_sources({'keywords':['vagas']})
        engine=create_async_engine(settings().database_url)
        try:
            sessions=async_sessionmaker(engine)
            async with sessions.begin() as db:
                actor=await db.get(User,UUID(actor_id))
                db.add(AdminAudit(actor_id=actor.id if actor else None,action='sync_completed',target_type='sources',details={key:value for key,value in result.items() if key!='search_channels'}))
            return result
        finally: await engine.dispose()
    return asyncio.run(execute())
