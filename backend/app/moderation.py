"""Private, explicitly allowlisted moderation API for recruitment ads."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import session
from app.models import Job, User
from app.schemas import JobOut, ModerationDecision
from app.security import current_user, role

router = APIRouter(prefix='/v1', tags=['Moderação'])


async def moderator(user: User = Depends(current_user)) -> User:
    allowed = {address.strip().casefold() for address in settings().moderator_emails}
    if not user.email_verified or (user.email.casefold() not in allowed and user.role not in {'super_admin','moderator'}):
        raise HTTPException(403, 'Esta área está disponível apenas para a equipe de moderação.')
    return user


@router.get('/moderation/jobs', response_model=list[JobOut])
async def pending_jobs(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), user: User = Depends(moderator), db: AsyncSession = Depends(session)):
    return (await db.scalars(select(Job).where(Job.moderation_status == 'pending', Job.active.is_(True)).order_by(Job.created_at, Job.id).offset(offset).limit(limit))).all()


@router.patch('/moderation/jobs/{job_id}', response_model=JobOut)
async def moderate_job(job_id: uuid.UUID, payload: ModerationDecision, user: User = Depends(moderator), db: AsyncSession = Depends(session)):
    job = await db.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if not job:
        raise HTTPException(404, 'Vaga não encontrada.')
    if job.recruiter_id == user.id:
        raise HTTPException(403, 'Sua própria vaga deve ser revisada por outro moderador.')
    if not job.active:
        raise HTTPException(409, 'A vaga já foi encerrada pelo contratante.')
    if payload.status == 'rejected' and not payload.note.strip():
        raise HTTPException(422, 'Informe o motivo da reprovação para orientar o contratante.')
    job.moderation_status = payload.status
    job.moderation_note = payload.note.strip() or None
    job.moderated_by = user.id
    job.moderated_at = datetime.now(timezone.utc)
    from app.admin import audit
    audit(db,user,'job_'+payload.status,'job',job.id,{'note':payload.note})
    if job.recruiter_id:
        from app.system_mail import queue_notice
        await queue_notice(db,job.recruiter_id,'Atualização da sua vaga no Vagou!',f'Vaga: {job.title}\nStatus: {payload.status}\nMotivo: {payload.note or "Revisão concluída."}')
    await db.commit()
    await db.refresh(job)
    return job


@router.get('/recruiter/jobs', response_model=list[JobOut])
async def recruiter_jobs(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), user: User = Depends(role('recruiter')), db: AsyncSession = Depends(session)):
    return (await db.scalars(select(Job).where(Job.recruiter_id == user.id).order_by(Job.created_at.desc(), Job.id).offset(offset).limit(limit))).all()


@router.get('/recruiter/moderation-summary')
async def recruiter_moderation_summary(user: User = Depends(role('recruiter')),
                                      db: AsyncSession = Depends(session)):
    query = (select(Job.moderation_status, Job.active, func.count(Job.id))
             .where(Job.recruiter_id == user.id)
             .group_by(Job.moderation_status, Job.active))
    totals = {'pending': 0, 'approved': 0, 'rejected': 0, 'closed': 0}
    for status, active, count in (await db.execute(query)).all():
        if not active:
            totals['closed'] += count
        else:
            totals[status] += count
    return {'counts': totals, 'guidance': {
        'pending': 'Em análise pela moderação.',
        'approved': 'Aprovada e visível aos candidatos.',
        'rejected': 'Confira o motivo informado na vaga e corrija antes de republicar.',
        'closed': 'Encerrada pelo recrutador.',
    }}
