import asyncio
import io
import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from pypdf import PdfReader
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.courses import COURSES
from app.db import session
from app.matching import eligible, evaluate_job, match, normalize
from app.models import Application, Job, User
from app.premium import has_premium_access
from app.schemas import DeleteAccount, JobCreate, JobOut, PublicJobOut, Preferences, ProfileUpdate, StatusUpdate
from app.security import cipher, current_user, role, verify_password
from app.services import apply, private_storage

router = APIRouter(prefix='/v1')
logger = logging.getLogger('uvicorn.error')
Candidate = Depends(role('candidate'))
Recruiter = Depends(role('recruiter'))
DB = Depends(session)


def account_view(user):
    return {'id': user.id, 'email': user.email, 'name': user.name, 'role': user.role, 'skills': user.skills,
            'is_premium': has_premium_access(user), 'automation_enabled': user.automation_enabled,
            'has_resume': bool(user.resume_key), 'preferences': user.preferences or {},
            'phone': cipher().decrypt(user.phone_encrypted.encode()).decode() if user.phone_encrypted else None,
            'email_verified': user.email_verified, 'company_cnpj': user.company_cnpj,
            'company_name': user.company_name, 'company_contact_email': user.company_contact_email,
            'profile_completion': round(100 * sum([bool(user.name), bool(user.skills),
                bool(user.phone_encrypted), bool(user.resume_key), bool((user.preferences or {}).get('titles'))]) / 5)}


@router.get('/me')
async def me(user: User = Depends(current_user)):
    return account_view(user)


@router.get('/candidate/entitlements')
async def candidate_entitlements(user: User = Candidate):
    premium = has_premium_access(user)
    return {'is_premium': premium, 'plan': 'premium' if premium else 'free',
            'automation_enabled': user.automation_enabled}


@router.put('/me/profile')
async def profile(payload: ProfileUpdate, user: User = Candidate, db: AsyncSession = DB):
    user.name = payload.name
    user.skills = payload.skills
    user.phone_encrypted = cipher().encrypt(payload.phone.encode()).decode() if payload.phone else None
    await db.commit()
    return account_view(user)


@router.put('/me/preferences')
async def preferences(payload: Preferences, user: User = Candidate, db: AsyncSession = DB):
    submitted = payload.model_dump(exclude_unset=True)
    automation_enabled = submitted.pop('automation_enabled', None)
    if automation_enabled is True and not has_premium_access(user):
        raise HTTPException(403, 'Premium subscription required')
    updated_preferences = dict(user.preferences or {})
    updated_preferences.update(submitted)
    user.preferences = updated_preferences
    if automation_enabled is not None:
        user.automation_enabled = automation_enabled
    await db.commit()
    return {**user.preferences, 'automation_enabled': user.automation_enabled}


@router.post('/me/courses/{course_id}')
async def declare_course_completion(course_id: str, user: User = Candidate, db: AsyncSession = DB):
    if course_id not in {course['id'] for course in COURSES}:
        raise HTTPException(404, 'Curso não encontrado no catálogo.')
    current = dict(user.preferences or {})
    completed = list(current.get('completed_course_ids') or [])
    if course_id not in completed:
        completed.append(course_id)
    current['completed_course_ids'] = completed
    user.preferences = current
    await db.commit()
    return {'completed_course_ids': completed, 'declaration': 'Informação declarada pelo candidato, sem verificação da instituição.'}


@router.delete('/me', status_code=204)
async def delete_account(payload: DeleteAccount, user: User = Depends(current_user), db: AsyncSession = DB):
    user = await db.scalar(select(User).where(User.id == user.id).with_for_update())
    if not user:
        raise HTTPException(401, 'Esta conta não está mais disponível.')
    if not await asyncio.to_thread(verify_password, payload.password, user.password_hash):
        raise HTTPException(401, 'Invalid credentials')
    # File removal first: storage errors must not silently orphan a sensitive file.
    if user.resume_key:
        path = settings().storage_dir / user.resume_key
        await asyncio.to_thread(path.unlink, missing_ok=True)
    await db.delete(user)
    await db.commit()
    return Response(status_code=204)


async def validated_pdf(file: UploadFile) -> bytes:
    try:
        if file.content_type != 'application/pdf':
            raise HTTPException(415, 'Only PDF is accepted')
        data = await file.read(settings().max_pdf_bytes + 1)
        if len(data) > settings().max_pdf_bytes:
            raise HTTPException(413, 'PDF exceeds 5 MiB')
        if not data.startswith(b'%PDF-'):
            raise HTTPException(422, 'Invalid PDF signature')
        def inspect():
            reader = PdfReader(io.BytesIO(data), strict=True)
            if reader.is_encrypted or not 1 <= len(reader.pages) <= 20:
                raise ValueError('Encrypted PDFs or more than 20 pages are unsupported')
            root = reader.trailer['/Root']
            if any(key in root for key in ['/OpenAction', '/AA', '/AcroForm']) or '/EmbeddedFiles' in root.get('/Names', {}):
                raise ValueError('Active content and embedded files are unsupported')
        try:
            await asyncio.to_thread(inspect)
        except Exception:
            raise HTTPException(422, 'PDF is malformed, encrypted, or contains unsupported active content') from None
        return data
    finally:
        await file.close()


@router.put('/me/resume')
async def upload_resume(file: UploadFile, user: User = Candidate, db: AsyncSession = DB):
    data = await validated_pdf(file)
    # A stable per-user key plus DB lock serializes upload/deletion.
    user = await db.scalar(select(User).where(User.id == user.id).with_for_update())
    if not user:
        raise HTTPException(401, 'Account no longer exists')
    root = private_storage(settings().storage_dir)
    key = str(user.id)
    destination = root / key
    temporary = root / str(uuid.uuid4())
    def persist():
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as output:
                output.write(cipher().encrypt(data))
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    await asyncio.to_thread(persist)
    user.resume_key = key
    await db.commit()
    return {'stored': True, 'bytes': len(data)}


@router.get('/me/resume')
async def download_resume(user: User = Candidate):
    if not user.resume_key:
        raise HTTPException(404, 'Resume not found')
    try:
        data = cipher().decrypt(await asyncio.to_thread((settings().storage_dir / user.resume_key).read_bytes))
    except FileNotFoundError:
        raise HTTPException(404, 'Resume not found') from None
    return StreamingResponse(io.BytesIO(data), media_type='application/pdf', headers={
        'Content-Disposition': 'attachment; filename="curriculo.pdf"', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


@router.post('/jobs', response_model=JobOut, status_code=201)
async def create_job(payload: JobCreate, user: User = Recruiter, db: AsyncSession = DB):
    job = Job(**payload.model_dump(), recruiter_id=user.id, moderation_status='pending')
    db.add(job)
    import logging
    await db.commit()
    await db.refresh(job)
    return job


@router.get('/jobs', response_model=list[PublicJobOut])
async def jobs(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
               title: str | None = Query(None, max_length=160), city: str | None = Query(None, max_length=80),
               state: str | None = Query(None, min_length=2, max_length=8),
               keywords: list[str] = Query(default=[], max_length=10), db: AsyncSession = DB):
    from app.worker import refresh_job_sources
    preferences = {'titles': [title] if title else [], 'keywords': keywords,
        'locations': [f'{city} / {state}' if state else city] if city else []}
    try:
        await refresh_job_sources(preferences)
    except Exception as error:
        logger.error('public_job_sync_failed error_type=%s', type(error).__name__)
    return (await db.scalars(select(Job).where(Job.active.is_(True), Job.moderation_status == 'approved').order_by(Job.created_at.desc(), Job.id).offset(offset).limit(limit))).all()

    logger = logging.getLogger('uvicorn.error')

@router.get('/jobs/{job_id}', response_model=PublicJobOut)
async def job_detail(job_id: uuid.UUID, db: AsyncSession = DB):
    job = await db.get(Job, job_id)
    if not job or not job.active or job.moderation_status != 'approved':
        raise HTTPException(404, 'Job not found')
    return job


@router.delete('/jobs/{job_id}', status_code=204)
async def close_job(job_id: uuid.UUID, user: User = Recruiter, db: AsyncSession = DB):
    job = await db.scalar(select(Job).where(Job.id == job_id, Job.recruiter_id == user.id).with_for_update())
    if not job:
        raise HTTPException(404, 'Job not found')
    job.active = False
    await db.commit()
    return Response(status_code=204)


@router.get('/matches')
async def matches(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), user: User = Candidate, db: AsyncSession = DB):
    from app.worker import refresh_job_sources
    collector_status = {'enabled': settings().enable_public_collectors, 'collected_jobs': 0, 'failed_sources': 0, 'configured': False}
    try:
        collector_status = await refresh_job_sources(user.preferences or {})
    except Exception as error:
        logger.error('candidate_match_source_sync_failed error_type=%s', type(error).__name__)
        collector_status['failed_sources'] = 1
    # Pagination is over active jobs examined; filters can make a page shorter.
    rows = (await db.scalars(select(Job).where(Job.active.is_(True), Job.moderation_status == 'approved').order_by(Job.created_at.desc(), Job.id).offset(offset).limit(limit))).all()
    items = []
    for job in rows:
        if not eligible(job, user.preferences):
            continue
        skill_match = match(user.skills, job.keywords)
        preference_match = evaluate_job(job, user.skills, user.preferences or {})
        items.append({'job': PublicJobOut.model_validate(job).model_dump(mode='json'),
            **skill_match, 'match_score': preference_match['match_score'],
            'match_reasons': preference_match['match_reasons'] + preference_match['missed_reasons']})
    return {'items': items, 'next_offset': offset + len(rows) if len(rows) == limit else None,
        'collector_status': collector_status}


@router.post('/jobs/{job_id}/applications')
async def manual_apply(job_id: uuid.UUID, user: User = Candidate, db: AsyncSession = DB):
    user = await db.scalar(select(User).where(User.id == user.id).with_for_update())
    if not user:
        raise HTTPException(401, 'Esta conta não está mais disponível.')
    job = await db.scalar(select(Job).where(Job.id == job_id, Job.active.is_(True), Job.moderation_status == 'approved').with_for_update())
    if not job:
        raise HTTPException(404, 'Job not found')
    if job.recruiter_id is None:
        if not job.source_url:
            raise HTTPException(409, 'Esta vaga ainda não possui um canal oficial de candidatura.')
        return {'created': False, 'status': 'requires_manual', 'external_url': job.source_url,
                'message': 'Conclua a candidatura no site oficial da vaga.'}
    if not user.resume_key:
        raise HTTPException(409, 'Envie seu currículo antes de se candidatar.')
    application_id, created = await apply(db, user, job, 'manual')
    await db.commit()
    return {'id': application_id, 'created': created, 'status': 'submitted'}


@router.get('/applications')
async def applications(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), user: User = Depends(current_user), db: AsyncSession = DB):
    query = select(Application, Job, User.name).select_from(Application).join(Job, Job.id == Application.job_id).join(User, User.id == Application.candidate_id)
    query = query.where(Application.candidate_id == user.id) if user.role == 'candidate' else query.where(Job.recruiter_id == user.id)
    rows = (await db.execute(query.order_by(Application.created_at.desc(), Application.id).offset(offset).limit(limit))).all()
    return [{'id': a.id, 'job_id': j.id, 'job_title': j.title, 'candidate_id': a.candidate_id,
             'source': a.source, 'status': a.status, 'match_score': a.match_score, 'created_at': a.created_at, 'status_updated_at': a.status_updated_at,
             'company': j.company, 'job_url': j.source_url, 'job_path': f'/v1/jobs/{j.id}',
             'source_name': j.source_name, 'candidate_name': candidate_name} for a, j, candidate_name in rows]


@router.get('/applications/{application_id}/resume')
async def recruiter_resume(application_id: uuid.UUID, user: User = Recruiter, db: AsyncSession = DB):
    candidate = await db.scalar(select(User).join(Application, Application.candidate_id == User.id).join(Job, Job.id == Application.job_id).where(Application.id == application_id, Job.recruiter_id == user.id))
    if not candidate:
        raise HTTPException(404, 'Application not found')
    return await download_resume(candidate)


@router.patch('/applications/{application_id}')
async def application_status(application_id: uuid.UUID, payload: StatusUpdate, user: User = Recruiter, db: AsyncSession = DB):
    application = await db.scalar(select(Application).join(Job).where(Application.id == application_id, Job.recruiter_id == user.id).with_for_update(of=Application))
    if not application:
        raise HTTPException(404, 'Application not found')
    application.status = payload.status
    application.status_updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {'id': application.id, 'status': application.status, 'status_updated_at': application.status_updated_at}


@router.get('/recruiter/applicants')
async def recruiter_applicants(
    job_id: uuid.UUID | None = None,
    min_match: int = Query(0, ge=0, le=100),
    location: str | None = Query(None, max_length=120),
    salary_ceiling: float | None = Query(None, ge=0, le=1000000),
    completed_course_id: str | None = Query(None, max_length=100),
    work_style: str | None = Query(None, pattern=r'^(remote|hybrid|onsite)$'),
    offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100),
    user: User = Recruiter, db: AsyncSession = DB,
):
    """Applicant filters for own jobs; no personal characteristics are inferred."""
    query = (select(Application, Job, User)
             .join(Job, Job.id == Application.job_id)
             .join(User, User.id == Application.candidate_id)
             .where(Job.recruiter_id == user.id, Application.match_score >= min_match)
             .order_by(Application.created_at.desc(), Application.id))
    if job_id is not None:
        query = query.where(Job.id == job_id)
    result = await db.stream(query.execution_options(yield_per=100))
    items = []
    matched = 0
    try:
        async for application, job, candidate in result:
            prefs = candidate.preferences or {}
            places = prefs.get('locations') or []
            modalities = prefs.get('modalities') or []
            declared_courses = prefs.get('completed_course_ids') or []
            if location and not any(normalize(location) in normalize(str(place)) for place in places):
                continue
            if salary_ceiling is not None and float(prefs.get('min_salary') or 0) > salary_ceiling:
                continue
            if completed_course_id and completed_course_id not in declared_courses:
                continue
            if work_style and work_style not in modalities:
                continue
            if matched >= offset:
                items.append({
                    'id': application.id, 'candidate_name': candidate.name,
                    'candidate_email': candidate.email,
                    'candidate_phone': cipher().decrypt(candidate.phone_encrypted.encode()).decode() if candidate.phone_encrypted else None,
                    'candidate_skills': candidate.skills or [],
                    'job_id': job.id, 'job_title': job.title, 'status': application.status,
                    'match_score': application.match_score, 'created_at': application.created_at,
                    'preferred_locations': places, 'salary_expectation': prefs.get('min_salary'),
                    'preferred_modalities': modalities,
                    'completed_course_ids': declared_courses, 'course_evidence': 'self_declared',
                    'work_style_fit': 'aligned' if job.modality in modalities else 'not_informed' if not modalities else 'different',
                })
                if len(items) > limit:
                    break
            matched += 1
    finally:
        await result.close()
    return {'items': items[:limit], 'next_offset': offset + limit if len(items) > limit else None,
            'filters_applied': {'min_match': min_match, 'location': location,
                                'salary_ceiling': salary_ceiling,
                                'completed_course_id': completed_course_id, 'work_style': work_style}}


@router.get('/recruiter/dashboard')
async def recruiter_dashboard(user: User = Recruiter, db: AsyncSession = DB):
    active_jobs = await db.scalar(select(func.count(Job.id)).where(
        Job.recruiter_id == user.id, Job.active.is_(True))) or 0
    totals = (await db.execute(select(
        func.count(Application.id),
        func.sum(case((Application.match_score >= 70, 1), else_=0)),
        func.sum(case((Application.status.in_(['interview', 'hired']), 1), else_=0)),
    ).join(Job, Job.id == Application.job_id).where(Job.recruiter_id == user.id))).one()
    applications_count = int(totals[0] or 0)
    strong_candidates = int(totals[1] or 0)
    converted = int(totals[2] or 0)
    job_rows = (await db.execute(select(Application.job_id, func.count(Application.id)).join(
        Job, Job.id == Application.job_id).where(Job.recruiter_id == user.id).group_by(Application.job_id))).all()
    return {'active_jobs': int(active_jobs), 'total_applications': applications_count,
        'strong_candidates': strong_candidates,
        'conversion_rate': round(converted * 100 / applications_count, 1) if applications_count else 0,
        'applications_by_job': {str(job_id): count for job_id, count in job_rows}}


@router.get('/notifications')
async def candidate_notifications(limit: int = Query(20, ge=1, le=50),
                                  user: User = Candidate, db: AsyncSession = DB):
    """Read-only inbox of employer status changes, without push claims."""
    query = (select(Application, Job)
             .join(Job, Job.id == Application.job_id)
             .where(Application.candidate_id == user.id, Application.status != 'submitted')
             .order_by(Application.status_updated_at.desc(), Application.id)
             .limit(limit))
    rows = (await db.execute(query)).all()
    return [{'application_id': application.id, 'job_title': job.title,
             'status': application.status, 'updated_at': application.status_updated_at}
            for application, job in rows]


@router.get('/dashboard')
async def dashboard(user: User = Candidate, db: AsyncSession = DB):
    rows = (await db.execute(select(Application.source, Application.status, func.count(Application.id), func.sum(Application.match_score)).where(Application.candidate_id == user.id).group_by(Application.source, Application.status))).all()
    total = sum(r[2] for r in rows)
    by_status = {}
    for _, status, count, _ in rows:
        by_status[status] = by_status.get(status, 0) + count
    observation = 0
    # Stream bounded batches instead of retaining the entire job catalog.
    result = await db.stream_scalars(select(Job).where(Job.active.is_(True), Job.moderation_status == 'approved').execution_options(yield_per=200))
    async for job in result:
        if eligible(job, user.preferences) and match(user.skills, job.keywords)['category'] == 'observation':
            observation += 1
    return {'total_applications': total, 'manual': sum(r[2] for r in rows if r[0] == 'manual'),
            'automatic': sum(r[2] for r in rows if r[0] == 'automatic'), 'observation_jobs': observation,
            'average_match_score': round(sum(r[3] for r in rows) / total, 2) if total else 0,
            'by_status': by_status, 'generated_at': datetime.now(timezone.utc)}


@router.get('/courses')
async def courses(skill: str | None = Query(None, max_length=80)):
    return [c for c in COURSES if skill is None or normalize(skill) in {normalize(x) for x in c['skills']}]
