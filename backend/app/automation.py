"""Authenticated read-only execution reports for the candidate who owns them."""
import asyncio
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation_models import AutomationEvent, AutomationRun
from app.db import session
from app.models import Application, Job, User
from app.job_catalog import unique_reasons
from app.matching import is_brazilian_job, job_location_details
from app.premium import has_premium_access
from app.schemas import AutomationEventsReport, AutomationRunRequest, AutomationRunStatusReport, AutomationRunsReport
from app.security import role

router = APIRouter(prefix='/v1/automation', tags=['Automação Premium'])


def premium(user: User):
    if not has_premium_access(user):
        raise HTTPException(403, 'Esta funcionalidade exige uma assinatura Premium.')


def event_view(event, application=None, job=None):
    facts = {key: getattr(event, key, None) if getattr(event, key, None) is not None else getattr(job, key, None)
             for key in ('description', 'contact_email', 'city', 'state', 'modality', 'contract_type', 'salary_min', 'salary_max')}
    if job is not None:
        facts['description'] = job.description
        facts['contact_email'] = job.contact_email
    geography = job_location_details(SimpleNamespace(location=event.location or getattr(job, 'location', ''),
        country=getattr(job, 'country', None), **{key: facts[key] for key in ('city', 'state', 'modality')}))
    facts.update(city=geography['city'], state=geography['state'], recruiter_email=facts['contact_email'])
    return {**facts, 'id': event.id, 'job_id': event.job_id, 'job_title': event.job_title,
            'job_url': event.job_url, 'status': event.status, 'detail': event.detail,
            'created_at': event.created_at, 'company': event.company, 'location': event.location,
            'source_name': event.source_name, 'match_score': event.match_score,
            'match_reasons': unique_reasons(event.match_reasons), 'external_url': event.job_url,
            'company_name': event.company, 'destination_channel': event.destination_channel,
            'delivery_status': application.delivery_status if application else None}


def run_view(run):
    return {'applications_submitted': run.submitted_applications, **{key: getattr(run, key) for key in ['id', 'status', 'started_at', 'finished_at',
        'collected_jobs', 'scanned_jobs', 'external_jobs_scanned', 'filtered_jobs', 'possible_match_jobs',
        'eligible_jobs', 'submitted_applications', 'manual_review_jobs', 'error_count', 'omitted_events', 'consent_granted', 'search_channels_count']}}


@router.get('/runs', response_model=AutomationRunsReport)
async def reports(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
                  user: User = Depends(role('candidate')), db: AsyncSession = Depends(session)):
    premium(user)
    runs = list((await db.scalars(select(AutomationRun).where(AutomationRun.candidate_id == user.id)
        .order_by(AutomationRun.started_at.desc(), AutomationRun.id).offset(offset).limit(limit))).all())
    # Lists are bounded; detailed events use an independently paginated endpoint.
    return {'items': [run_view(run) for run in runs], 'next_offset': offset + len(runs) if len(runs) == limit else None}


@router.get('/runs/{run_id}/events', response_model=AutomationEventsReport)
async def report_events(run_id: UUID, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                        status: Literal['submitted', 'already_applied', 'requires_manual', 'possible_match', 'missing_resume', 'filtered', 'failed', 'limit_reached', 'search_channel'] | None = None,
                        user: User = Depends(role('candidate')), db: AsyncSession = Depends(session)):
    premium(user)
    run = await db.scalar(select(AutomationRun).where(AutomationRun.id == run_id, AutomationRun.candidate_id == user.id))
    if not run:
        raise HTTPException(404, 'Relatório não encontrado.')
    query = select(AutomationEvent).where(AutomationEvent.run_id == run.id)
    if status:
        query = query.where(AutomationEvent.status == status)
    events = list((await db.scalars(query
        .order_by(AutomationEvent.created_at, AutomationEvent.id).offset(offset).limit(limit))).all())
    job_ids = {event.job_id for event in events if event.job_id}
    applications = (await db.scalars(select(Application).where(
        Application.candidate_id == user.id, Application.job_id.in_(job_ids)))).all() if job_ids else []
    by_job = {application.job_id: application for application in applications}
    jobs = (await db.scalars(select(Job).where(Job.id.in_(job_ids)))).all() if job_ids else []
    vacancies = {job.id: job for job in jobs}
    items = []
    for event in events:
        job = vacancies.get(event.job_id)
        # Hide legacy foreign vacancy cards while retaining their immutable
        # audit rows and the original execution totals in the database.
        if event.job_id or event.job_title and event.status != 'search_channel':
            geography = job or SimpleNamespace(location=event.location, city=getattr(event, 'city', None),
                state=getattr(event, 'state', None), modality=getattr(event, 'modality', None), country=None)
            if not is_brazilian_job(geography):
                continue
        items.append(event_view(event, by_job.get(event.job_id), job))
    return {'run': run_view(run), 'items': items,
            'next_offset': offset + len(events) if len(events) == limit else None}


@router.post('/run', status_code=202)
async def enqueue_now(payload: AutomationRunRequest | None = None, user: User = Depends(role('candidate')), db: AsyncSession = Depends(session)):
    """Request an immediate cycle; server state is authoritative for Premium."""
    premium(user)
    if not user.automation_enabled:
        raise HTTPException(409, 'Ative e salve suas preferências de envio automático primeiro.')
    if payload is not None and not payload.consent_granted:
        raise HTTPException(409, 'É necessário autorizar o uso do currículo nesta rodada.')
    if not user.resume_key:
        raise HTTPException(409, 'Envie seu currículo PDF antes de iniciar os envios.')
    prefs = user.preferences or {}
    if not any(prefs.get(key) for key in ('modalities', 'titles', 'locations', 'contract_types', 'keywords', 'min_salary')):
        raise HTTPException(409, 'Configure ao menos um critério de busca antes de iniciar.')
    run = AutomationRun(candidate_id=user.id, status='queued', consent_granted=True, scanned_jobs=0, filtered_jobs=0,
        external_jobs_scanned=0, possible_match_jobs=0, eligible_jobs=0,
        submitted_applications=0, manual_review_jobs=0, error_count=0, omitted_events=0)
    db.add(run)
    await db.commit()
    try:
        from app.worker import run_automation
        await asyncio.to_thread(run_automation.apply_async,
            args=[str(user.id), True, str(run.id)], task_id=str(run.id))
    except Exception:
        run.status = 'failed'
        run.finished_at = datetime.now(timezone.utc)
        run.error_count = 1
        await db.commit()
        raise HTTPException(503, 'Não foi possível agendar a busca agora. O serviço tentará novamente no próximo ciclo.') from None
    return {'status': 'queued', 'run_id': str(run.id), 'message': 'Busca iniciada. O progresso aparece aqui.'}


@router.get('/runs/{run_id}/status', response_model=AutomationRunStatusReport)
async def run_status(run_id: UUID, user: User = Depends(role('candidate')), db: AsyncSession = Depends(session)):
    premium(user)
    run = await db.scalar(select(AutomationRun).where(AutomationRun.id == run_id,
        AutomationRun.candidate_id == user.id))
    if not run:
        raise HTTPException(404, 'Relatório não encontrado.')
    state, progress = run.status, {}
    if run.status in ('queued', 'running'):
        from app.worker import celery
        def task_progress():
            result = celery.AsyncResult(str(run.id))
            return result.state, result.info if isinstance(result.info, dict) else {}
        task_state, progress = await asyncio.to_thread(task_progress)
        state = {'PENDING': 'queued', 'PROGRESS': 'running', 'SUCCESS': 'complete', 'FAILURE': 'failed'}.get(task_state, run.status)
    return {**run_view(run), 'status': state, 'progress': progress}
