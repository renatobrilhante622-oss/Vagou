"""Brazilian catalog maintenance without deleting application audit history."""
import logging
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models import Job

logger = logging.getLogger(__name__)


async def quarantine_non_brazilian_jobs() -> int:
    """Archive foreign/unverifiable active ads in bounded, restartable batches.

    Applications, notification receipts and historical events remain intact.
    No country, address, employer or replacement vacancy is fabricated.
    """
    from app.matching import job_location_details

    engine = create_async_engine(settings().database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    archived = 0
    cursor = None
    try:
        while True:
            async with sessions.begin() as db:
                query = select(Job.id, Job.location, Job.city, Job.state, Job.country,
                               Job.modality, Job.title).where(Job.active.is_(True)).order_by(Job.id).limit(500)
                if cursor:
                    query = query.where(Job.id > cursor)
                rows = (await db.execute(query)).all()
                if not rows:
                    break
                expired = set((await db.scalars(select(Job.id).where(Job.id.in_([row.id for row in rows]), Job.expires_at <= datetime.now(timezone.utc)))).all())
                excluded = []
                repairs = []
                for row in rows:
                    observed = job_location_details(SimpleNamespace(**row._mapping))
                    if row.id in expired or not observed['is_brazilian']:
                        excluded.append(row.id)
                        continue
                    values = {'city': observed['city'], 'state': observed['state'], 'country': 'BR'}
                    if any(getattr(row, key) != value for key, value in values.items()):
                        repairs.append({'id': row.id, **values})
                if excluded:
                    result = await db.execute(update(Job).where(Job.id.in_(excluded), Job.active.is_(True)).values(active=False))
                    archived += result.rowcount
                if repairs:
                    await db.execute(update(Job), repairs)
                cursor = rows[-1].id
        if archived:
            logger.info('brazil_catalog_archived count=%s', archived)
        return archived
    finally:
        await engine.dispose()


def unique_reasons(values) -> list[str]:
    """Keep readable evidence once, including legacy duplicated event payloads."""
    seen = set()
    result = []
    for value in ([values] if isinstance(values, str) else values or []):
        if not isinstance(value, str):
            continue
        value = ' '.join(value.split()).strip()
        key = value.casefold().rstrip(' .;')
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result
