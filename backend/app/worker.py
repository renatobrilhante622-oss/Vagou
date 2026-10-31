"""Periodic, at-least-once automation with transactional idempotency.

An application is an internal submission visible to the owning recruiter.
This worker does not submit to third-party job sites or bypass their terms.
"""
import asyncio

from celery import Celery
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.matching import eligible, match
from app.models import Job, User
from app.services import apply

celery = Celery('vagou', broker=settings().redis_url)
celery.conf.update(
    task_serializer='json', accept_content=['json'], result_serializer='json',
    task_ignore_result=True, task_acks_late=True, worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    beat_schedule={'premium-automation': {'task': 'vagou.automate', 'schedule': 60.0}},
)


async def automate():
    # Each task owns its engine/event loop, avoiding pooled cross-loop connections.
    engine = create_async_engine(settings().database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    submitted = 0
    try:
        cursor = None
        while True:
            async with sessions() as db:
                query = select(User.id).where(User.role == 'candidate', User.is_premium.is_(True), User.automation_enabled.is_(True), User.resume_key.is_not(None)).order_by(User.id).limit(100)
                if cursor:
                    query = query.where(User.id > cursor)
                ids = list((await db.scalars(query)).all())
            if not ids:
                break
            for user_id in ids:
                async with sessions.begin() as db:
                    user = await db.scalar(select(User).where(User.id == user_id).with_for_update(skip_locked=True))
                    if not user or not user.is_premium or not user.automation_enabled or not user.resume_key:
                        continue
                    job_cursor = None
                    while True:
                        query = select(Job).where(Job.active.is_(True)).order_by(Job.id).limit(200)
                        if job_cursor:
                            query = query.where(Job.id > job_cursor)
                        jobs = list((await db.scalars(query)).all())
                        if not jobs:
                            break
                        for job in jobs:
                            if eligible(job, user.preferences) and match(user.skills, job.keywords)['category'] == 'high':
                                # Closure and submission serialize on the same row.
                                locked = await db.scalar(select(Job).where(Job.id == job.id, Job.active.is_(True)).with_for_update())
                                if locked:
                                    _, created = await apply(db, user, locked, 'automatic')
                                    submitted += int(created)
                        job_cursor = jobs[-1].id
            cursor = ids[-1]
        return submitted
    finally:
        await engine.dispose()


@celery.task(name='vagou.automate', autoretry_for=(ConnectionError, OperationalError), retry_backoff=True, max_retries=3)
def run_automation():
    return asyncio.run(automate())