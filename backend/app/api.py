import asyncio
import io
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from pypdf import PdfReader
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.courses import COURSES
from app.db import session
from app.matching import eligible, match, normalize
from app.models import Application, Job, User
from app.schemas import DeleteAccount, JobCreate, JobOut, Login, Preferences, ProfileUpdate, Register, StatusUpdate
from app.security import DUMMY_HASH, cipher, current_user, hash_password, role, token, verify_password
from app.services import apply, private_storage

router = APIRouter(prefix='/v1')
Candidate = Depends(role('candidate'))
Recruiter = Depends(role('recruiter'))
DB = Depends(session)


def account_view(user):
    return {'id': user.id, 'email': user.email, 'name': user.name, 'role': user.role, 'skills': user.skills,
            'is_premium': user.is_premium, 'automation_enabled': user.automation_enabled,
            'has_resume': bool(user.resume_key), 'preferences': user.preferences}


@router.post('/auth/register', status_code=201)
async def register(payload: Register, db: AsyncSession = DB):
    if payload.privacy_version != settings().privacy_version:
        raise HTTPException(422, 'Accept the current privacy policy version')
    user = User(email=str(payload.email).casefold(), name=payload.name, role=payload.role,
                password_hash=await asyncio.to_thread(hash_password, payload.password), privacy_version=payload.privacy_version)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, 'Registration unavailable for this email') from None
    return account_view(user)


@router.post('/auth/login')
async def login(payload: Login, db: AsyncSession = DB):
    user = await db.scalar(select(User).where(User.email == str(payload.email).casefold()))
    valid = await asyncio.to_thread(verify_password, payload.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid:
        raise HTTPException(401, 'Invalid credentials')
    return {'access_token': token(user), 'token_type': 'bearer', 'expires_in': settings().access_minutes * 60}


@router.post('/auth/logout', status_code=204)
async def logout(user: User = Depends(current_user), db: AsyncSession = DB):
    # Lock prevents lost increments during simultaneous logout requests.
    user = await db.scalar(select(User).where(User.id == user.id).with_for_update())
    user.token_version += 1
    await db.commit()
    return Response(status_code=204)


@router.get('/me')
async def me(user: User = Depends(current_user)):
    return account_view(user)


@router.put('/me/profile')
async def profile(payload: ProfileUpdate, user: User = Candidate, db: AsyncSession = DB):
    user.name = payload.name
    user.skills = payload.skills
    user.phone_encrypted = cipher().encrypt(payload.phone.encode()).decode() if payload.phone else None
    await db.commit()
    return account_view(user)


@router.put('/me/preferences')
async def preferences(payload: Preferences, user: User = Candidate, db: AsyncSession = DB):
    if payload.automation_enabled and not user.is_premium:
        raise HTTPException(403, 'Premium subscription required')
    user.preferences = payload.model_dump(exclude={'automation_enabled'})
    user.automation_enabled = payload.automation_enabled
    await db.commit()
    return {**user.preferences, 'automation_enabled': user.automation_enabled}


@router.delete('/me', status_code=204)
async def delete_account(payload: DeleteAccount, user: User = Depends(current_user), db: AsyncSession = DB):
    user = await db.scalar(select(User).where(User.id == user.id).with_for_update())
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
    job = Job(**payload.model_dump(), recruiter_id=user.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


@router.get('/jobs', response_model=list[JobOut])
async def jobs(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), db: AsyncSession = DB):
    return (await db.scalars(select(Job).where(Job.active.is_(True)).order_by(Job.created_at.desc(), Job.id).offset(offset).limit(limit))).all()


@router.get('/jobs/{job_id}', response_model=JobOut)
async def job_detail(job_id: uuid.UUID, db: AsyncSession = DB):
    job = await db.get(Job, job_id)
    if not job or not job.active:
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
    # Pagination is over active jobs examined; filters can make a page shorter.
    rows = (await db.scalars(select(Job).where(Job.active.is_(True)).order_by(Job.created_at.desc(), Job.id).offset(offset).limit(limit))).all()
    return {'items': [{'job': JobOut.model_validate(j).model_dump(mode='json'), **match(user.skills, j.keywords)} for j in rows if eligible(j, user.preferences)], 'next_offset': offset + len(rows) if len(rows) == limit else None}


@router.post('/jobs/{job_id}/applications')
async def manual_apply(job_id: uuid.UUID, user: User = Candidate, db: AsyncSession = DB):
    user = await db.scalar(select(User).where(User.id == user.id).with_for_update())
    job = await db.scalar(select(Job).where(Job.id == job_id, Job.active.is_(True)).with_for_update())
    if not job:
        raise HTTPException(404, 'Job not found')
    if not user.resume_key:
        raise HTTPException(409, 'Upload your resume before applying')
    application_id, created = await apply(db, user, job, 'manual')
    await db.commit()
    return {'id': application_id, 'created': created, 'status': 'submitted'}


@router.get('/applications')
async def applications(offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), user: User = Depends(current_user), db: AsyncSession = DB):
    query = select(Application, Job).join(Job, Job.id == Application.job_id)
    query = query.where(Application.candidate_id == user.id) if user.role == 'candidate' else query.where(Job.recruiter_id == user.id)
    rows = (await db.execute(query.order_by(Application.created_at.desc(), Application.id).offset(offset).limit(limit))).all()
    return [{'id': a.id, 'job_id': j.id, 'job_title': j.title, 'candidate_id': a.candidate_id,
             'source': a.source, 'status': a.status, 'match_score': a.match_score, 'created_at': a.created_at} for a, j in rows]


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
    await db.commit()
    return {'id': application.id, 'status': application.status}


@router.get('/dashboard')
async def dashboard(user: User = Candidate, db: AsyncSession = DB):
    rows = (await db.execute(select(Application.source, Application.status, func.count(Application.id), func.sum(Application.match_score)).where(Application.candidate_id == user.id).group_by(Application.source, Application.status))).all()
    total = sum(r[2] for r in rows)
    by_status = {}
    for _, status, count, _ in rows:
        by_status[status] = by_status.get(status, 0) + count
    observation = 0
    # Stream bounded batches instead of retaining the entire job catalog.
    result = await db.stream_scalars(select(Job).where(Job.active.is_(True)).execution_options(yield_per=200))
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
