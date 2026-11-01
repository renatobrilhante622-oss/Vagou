import uuid
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.matching import match
from app.models import Application, Job, User


async def apply(db: AsyncSession, user: User, job: Job, source: str, *, score: int | None = None, status: str = 'submitted') -> tuple[uuid.UUID, bool]:
    application_id = uuid.uuid4()
    statement = insert(Application).values(
        id=application_id, candidate_id=user.id, job_id=job.id, source=source,
        status=status, match_score=score if score is not None else match(user.skills, job.keywords)['match_score'],
    ).on_conflict_do_nothing(constraint='uq_application_candidate_job').returning(Application.id)
    inserted = (await db.execute(statement)).scalar_one_or_none()
    if inserted:
        return inserted, True
    from sqlalchemy import select
    existing = await db.scalar(select(Application.id).where(Application.candidate_id == user.id, Application.job_id == job.id))
    return existing, False


def private_storage(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    return root