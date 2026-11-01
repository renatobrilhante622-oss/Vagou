"""Audited staff commands. Public signup cannot grant administrative roles."""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.access import is_admin, is_owner
from app.db import session
from app.models import (
    User,
    Job,
    Application,
    ApplicationNotification,
    AdminAudit,
    SystemNotification,
)
from app.automation_models import AutomationRun
from app.schemas import AdminUserUpdate, AdminJobAction, JobCreate, JobOut
from app.security import current_user, cipher

router = APIRouter(prefix="/v1/admin", tags=["Central de Comando"])


async def staff(user: User = Depends(current_user)):
    if not is_admin(user):
        raise HTTPException(403, "Acesso exclusivo da equipe de moderação.")
    return user


async def manager(user: User = Depends(staff)):
    if user.role != "super_admin":
        raise HTTPException(
            403, "Somente Super Admin pode gerenciar contas, planos e equipe."
        )
    return user


def audit(db, actor, action, target_type, target_id=None, details=None):
    db.add(
        AdminAudit(
            actor_id=actor.id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details or {},
        )
    )


def user_view(user):
    from app.premium import has_premium_access

    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "is_premium": has_premium_access(user),
        "email_verified": user.email_verified,
        "company_name": user.company_name,
        "company_cnpj": user.company_cnpj,
        "company_contact_email": user.company_contact_email,
        "company_verified": user.company_verified,
        "phone": (
            cipher().decrypt(user.phone_encrypted.encode()).decode()
            if user.phone_encrypted
            else None
        ),
    }


@router.get("/dashboard")
async def dashboard(actor: User = Depends(staff), db: AsyncSession = Depends(session)):
    async def count(model, *where):
        return (
            await db.scalar(select(func.count()).select_from(model).where(*where)) or 0
        )

    from app.premium import premium_test_emails

    pro = or_(
        User.is_premium.is_(True),
        func.lower(User.email).in_(premium_test_emails() | {"rbrilhante001@gmail.com"}),
    )
    latest = await db.scalar(
        select(AdminAudit)
        .where(AdminAudit.action == "sync_completed")
        .order_by(AdminAudit.created_at.desc())
        .limit(1)
    )
    return {
        "candidates": await count(User, User.role == "candidate"),
        "active_pro": await count(User, User.is_active.is_(True), pro),
        "companies": await count(User, User.role == "recruiter"),
        "internal_jobs": await count(
            Job, Job.recruiter_id.is_not(None), Job.active.is_(True)
        ),
        "external_jobs": await count(
            Job, Job.recruiter_id.is_(None), Job.active.is_(True)
        ),
        "pending_moderation": await count(
            Job, Job.moderation_status == "pending", Job.active.is_(True)
        ),
        "automation_runs": await count(AutomationRun),
        "applications": await count(Application),
        "last_sync": (
            {"at": latest.created_at, "result": latest.details} if latest else None
        ),
    }


@router.get("/jobs", response_model=list[JobOut])
async def jobs(
    status: str | None = Query(None, pattern="^(pending|approved|rejected)$"),
    external: bool | None = None,
    recruiter_id: uuid.UUID | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    actor: User = Depends(staff),
    db: AsyncSession = Depends(session),
):
    query = select(Job)
    if status:
        query = query.where(Job.moderation_status == status)
    if external is not None:
        query = query.where(
            Job.recruiter_id.is_(None) if external else Job.recruiter_id.is_not(None)
        )
    if recruiter_id:
        query = query.where(Job.recruiter_id == recruiter_id)
    return (
        await db.scalars(
            query.order_by(Job.created_at.desc(), Job.id).offset(offset).limit(limit)
        )
    ).all()


@router.post("/jobs", response_model=JobOut, status_code=201)
async def publish(
    payload: JobCreate,
    actor: User = Depends(staff),
    db: AsyncSession = Depends(session),
):
    from app.matching import is_brazilian_job

    job = Job(
        **payload.model_dump(),
        recruiter_id=actor.id,
        source_name="Vagou! Oficial",
        moderation_status="approved",
        moderated_by=actor.id,
        moderated_at=datetime.now(timezone.utc),
    )
    if not is_brazilian_job(job):
        raise HTTPException(422, "Informe uma localização brasileira verificável.")
    db.add(job)
    await db.flush()
    audit(db, actor, "official_job_created", "job", job.id)
    await db.commit()
    await db.refresh(job)
    return job


@router.put("/jobs/{job_id}", response_model=JobOut)
async def edit(
    job_id: uuid.UUID,
    payload: JobCreate,
    actor: User = Depends(staff),
    db: AsyncSession = Depends(session),
):
    job = await db.get(Job, job_id, with_for_update=True)
    if not job:
        raise HTTPException(404, "Vaga não encontrada.")
    from app.matching import is_brazilian_job

    for key, value in payload.model_dump().items():
        setattr(job, key, value)
    if not is_brazilian_job(job):
        raise HTTPException(422, "Informe localização brasileira verificável.")
    job.moderated_by = actor.id
    job.moderated_at = datetime.now(timezone.utc)
    audit(db, actor, "job_edited", "job", job.id)
    await db.commit()
    await db.refresh(job)
    return job


@router.post("/jobs/{job_id}/actions", response_model=JobOut)
async def action(
    job_id: uuid.UUID,
    payload: AdminJobAction,
    actor: User = Depends(staff),
    db: AsyncSession = Depends(session),
):
    job = await db.get(Job, job_id, with_for_update=True)
    if not job:
        raise HTTPException(404, "Vaga não encontrada.")
    if payload.action == "reject" and not payload.note.strip():
        raise HTTPException(422, "Informe o motivo da rejeição.")
    if (
        job.recruiter_id == actor.id
        and payload.action in {"approve", "reject"}
        and actor.role != "super_admin"
    ):
        raise HTTPException(403, "Outro moderador precisa revisar sua vaga.")
    if payload.action == "approve":
        from app.matching import is_brazilian_job

        if not is_brazilian_job(job):
            raise HTTPException(422, "Localização brasileira não confirmada.")
        recruiter = await db.get(User, job.recruiter_id) if job.recruiter_id else None
        if recruiter and not recruiter.is_active:
            raise HTTPException(409, "Reative a empresa antes de aprovar anúncios.")
        job.moderation_status = "approved"
        job.active = True
    elif payload.action == "reject":
        job.moderation_status = "rejected"
    elif payload.action == "delete":
        job.active = False
    else:
        job.featured = payload.action == "feature"
    job.moderated_by = actor.id
    job.moderated_at = datetime.now(timezone.utc)
    job.moderation_note = payload.note or None
    audit(db, actor, "job_" + payload.action, "job", job.id, {"note": payload.note})
    if job.recruiter_id and payload.action in {"reject", "approve"}:
        from app.system_mail import queue_notice

        await queue_notice(
            db,
            job.recruiter_id,
            "Atualização da sua vaga no Vagou!",
            f'Vaga: {job.title}\nStatus: {job.moderation_status}\nMotivo: {payload.note or "Revisão concluída."}',
        )
    await db.commit()
    await db.refresh(job)
    return job


@router.get("/companies")
async def companies(
    q: str = Query("", max_length=120),
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    actor: User = Depends(staff),
    db: AsyncSession = Depends(session),
):
    query = select(User).where(User.role == "recruiter")
    if q:
        query = query.where(
            or_(
                User.name.ilike("%" + q + "%"),
                User.company_name.ilike("%" + q + "%"),
                User.company_cnpj.ilike("%" + q + "%"),
            )
        )
    rows = (
        await db.scalars(
            query.order_by(User.created_at.desc(), User.id).offset(offset).limit(limit)
        )
    ).all()
    return [user_view(user) for user in rows]


@router.get("/users")
async def users(
    q: str = Query("", max_length=120),
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    actor: User = Depends(manager),
    db: AsyncSession = Depends(session),
):
    query = select(User)
    if q:
        query = query.where(
            or_(User.name.ilike("%" + q + "%"), User.email.ilike("%" + q + "%"))
        )
    rows = (
        await db.scalars(
            query.order_by(User.created_at.desc(), User.id).offset(offset).limit(limit)
        )
    ).all()
    return [user_view(user) for user in rows]


@router.patch("/users/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    actor: User = Depends(staff),
    db: AsyncSession = Depends(session),
):
    fields = payload.model_dump(exclude_unset=True, exclude={"note"})
    if any(value is None for value in fields.values()):
        raise HTTPException(422, "Informe valores válidos para as permissões.")
    if actor.role != "super_admin" and set(fields) - {"company_verified"}:
        raise HTTPException(403, "Ação exclusiva de Super Admin.")
    user = await db.get(User, user_id, with_for_update=True)
    if not user:
        raise HTTPException(404, "Conta não encontrada.")
    if is_owner(user):
        raise HTTPException(
            409, "A conta proprietária mantém Super Admin e PRO vitalício."
        )
    if user.id == actor.id and any(
        key in fields for key in ("role", "is_active", "email_verified")
    ):
        raise HTTPException(409, "Não altere seu próprio acesso administrativo.")
    from app.company import valid_cnpj

    if (
        fields.get("company_verified") is True
        and user.company_cnpj
        and not valid_cnpj(user.company_cnpj)
    ):
        raise HTTPException(409, "Confira o CNPJ antes da verificação KYB.")
    if fields.get("company_verified") is True and (
        user.role != "recruiter" or not user.company_cnpj or not user.email_verified
    ):
        raise HTTPException(
            409, "Confirme o cadastro empresarial e o e-mail antes da verificação KYB."
        )
    if fields.get("role") == "recruiter" and not all(
        [user.company_cnpj, user.company_name, user.company_contact_email]
    ):
        raise HTTPException(
            409, "Complete os dados empresariais antes de atribuir o papel Recrutador."
        )
    for key, value in fields.items():
        setattr(user, key, value)
    if set(fields) & {"role", "is_active", "email_verified"}:
        user.token_version += 1
    if fields.get("is_premium") is False:
        user.automation_enabled = False
    if fields.get("is_active") is False:
        user.automation_enabled = False
        from sqlalchemy import update

        await db.execute(
            update(Job).where(Job.recruiter_id == user.id).values(active=False)
        )
    audit(db, actor, "user_updated", "user", user.id, {**fields, "note": payload.note})
    await db.commit()
    return user_view(user)


@router.post("/sync", status_code=202)
async def sync(actor: User = Depends(staff), db: AsyncSession = Depends(session)):
    from app.worker import sync_admin_sources

    try:
        task = sync_admin_sources.delay(str(actor.id))
    except Exception:
        raise HTTPException(
            503, "Não foi possível agendar a sincronização. Tente novamente."
        ) from None
    audit(db, actor, "sync_requested", "sources", details={"task_id": str(task.id)})
    await db.commit()
    return {"task_id": str(task.id), "status": "queued"}


@router.post("/cleanup")
async def cleanup(actor: User = Depends(staff), db: AsyncSession = Depends(session)):
    from app.job_catalog import quarantine_non_brazilian_jobs

    count = await quarantine_non_brazilian_jobs()
    rows = (await db.scalars(select(Job).where(Job.active.is_(True)))).all()
    invalid = [
        job
        for job in rows
        if len(job.description.strip()) < 30
        or (job.recruiter_id is None and not job.source_url)
    ]
    for job in invalid:
        job.active = False
    audit(
        db, actor, "catalog_cleanup", "jobs", details={"archived": count + len(invalid)}
    )
    await db.commit()
    return {
        "archived": count + len(invalid),
        "message": "Anúncios inválidos foram arquivados; auditorias e candidaturas preservadas.",
    }


@router.get("/audit")
async def audit_log(
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    actor: User = Depends(staff),
    db: AsyncSession = Depends(session),
):
    actions = (
        await db.scalars(
            select(AdminAudit)
            .order_by(AdminAudit.created_at.desc(), AdminAudit.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    runs = (
        await db.scalars(
            select(AutomationRun).order_by(AutomationRun.started_at.desc()).limit(limit)
        )
    ).all()
    mail = (
        await db.execute(
            select(ApplicationNotification.status, func.count()).group_by(
                ApplicationNotification.status
            )
        )
    ).all()
    total = sum(count for _, count in mail)
    sent = sum(count for status, count in mail if status == "sent")
    return {
        "actions": [
            {
                "id": a.id,
                "actor_id": a.actor_id,
                "action": a.action,
                "target_type": a.target_type,
                "target_id": a.target_id,
                "details": a.details,
                "created_at": a.created_at,
            }
            for a in actions
        ],
        "runs": [
            {
                "id": r.id,
                "candidate_id": r.candidate_id,
                "status": r.status,
                "scanned_jobs": r.scanned_jobs,
                "applications_submitted": r.submitted_applications,
                "possible_match_jobs": r.possible_match_jobs,
                "error_count": r.error_count,
                "started_at": r.started_at,
            }
            for r in runs
        ],
        "smtp": dict(mail),
        "smtp_acceptance_rate": round(sent * 100 / total, 1) if total else 0,
    }
