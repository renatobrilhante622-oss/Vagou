"""Authenticated read-only execution reports for the candidate who owns them."""
import asyncio
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation_models import AutomationEvent, AutomationRun
from app.db import session
from app.entitlements import can_automate
from app.models import User
from app.security import role

router = APIRouter(prefix='/v1/automation', tags=['Automação Premium'])


def premium(user: User):
    if not can_automate(user):
        raise HTTPException(403, {'code': 'premium_required', 'message': 'Esta funcionalidade exige plano Premium ou acesso de teste autorizado.'})


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


@router.post('/run', status_code=202)
async def enqueue_now(request: Request, user: User = Depends(role('candidate'))):
    """Request an immediate cycle; server state is authoritative for Premium."""
    premium(user)
    if not user.automation_enabled:
        raise HTTPException(409, {'code': 'automation_disabled', 'message': 'Ative e salve suas preferências de envio automático primeiro.'})
    if not user.resume_key:
        raise HTTPException(409, {'code': 'resume_required', 'message': 'Envie seu currículo PDF antes de iniciar os envios.'})
    prefs = user.preferences or {}
    if not prefs.get('titles') or not prefs.get('modalities'):
        raise HTTPException(409, {'code': 'preferences_required', 'message': 'Configure os cargos e modalidades de interesse antes de iniciar.'})
    marker = str(uuid4())
    key = f'automation:dispatch:{user.id}'
    redis = request.app.state.redis
    try:
        acquired = await redis.set(key, marker, ex=30, nx=True)
        if not acquired:
            return {'status': 'queued', 'deduplicated': True,
                    'message': 'Sua busca já foi solicitada. Acompanhe os relatórios.'}
        from app.worker import run_automation
        await asyncio.to_thread(run_automation.apply_async, args=[str(user.id)],
                                kwargs={'force': True}, task_id=marker)
    except Exception:
        # Release only our own reservation; never remove a later request's lock.
        try:
            await redis.eval("if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) else return 0 end", 1, key, marker)
        except Exception:
            pass
        raise HTTPException(503, 'Não foi possível agendar a busca agora. O serviço tentará novamente no próximo ciclo.') from None
    return {'status': 'queued', 'task_id': marker, 'deduplicated': False,
            'message': 'Busca agendada para sua conta. Acompanhe os resultados em Relatórios.'}
