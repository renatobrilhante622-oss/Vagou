"""Authenticated read-only execution reports for the candidate who owns them."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation_models import AutomationEvent, AutomationRun
from app.db import session
from app.models import User
from app.security import role

router = APIRouter(prefix='/v1/automation', tags=['Automação Premium'])


def premium(user: User):
    if not user.is_premium:
        raise HTTPException(403, 'Esta funcionalidade exige uma assinatura Premium.')


def event_view(event):
    return {'id': event.id, 'job_id': event.job_id, 'job_title': event.job_title,
            'job_url': event.job_url, 'status': event.status, 'detail': event.detail,
            'created_at': event.created_at}


def run_view(run):
    return {key: getattr(run, key) for key in ['id', 'status', 'started_at', 'finished_at',
        'scanned_jobs', 'eligible_jobs', 'submitted_applications', 'manual_review_jobs', 'error_count', 'omitted_events']}


@router.get('/runs')
async def reports(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
                  user: User = Depends(role('candidate')), db: AsyncSession = Depends(session)):
    premium(user)
    runs = list((await db.scalars(select(AutomationRun).where(AutomationRun.candidate_id == user.id)
        .order_by(AutomationRun.started_at.desc(), AutomationRun.id).offset(offset).limit(limit))).all())
    # Lists are bounded; detailed events use an independently paginated endpoint.
    return {'items': [run_view(run) for run in runs], 'next_offset': offset + len(runs) if len(runs) == limit else None}


@router.get('/runs/{run_id}/events')
async def report_events(run_id: UUID, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                        user: User = Depends(role('candidate')), db: AsyncSession = Depends(session)):
    premium(user)
    run = await db.scalar(select(AutomationRun).where(AutomationRun.id == run_id, AutomationRun.candidate_id == user.id))
    if not run:
        raise HTTPException(404, 'Relatório não encontrado.')
    events = list((await db.scalars(select(AutomationEvent).where(AutomationEvent.run_id == run.id)
        .order_by(AutomationEvent.created_at, AutomationEvent.id).offset(offset).limit(limit))).all())
    return {'run': run_view(run), 'items': [event_view(event) for event in events],
            'next_offset': offset + len(events) if len(events) == limit else None}
