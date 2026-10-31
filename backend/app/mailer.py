"""Durable confirmation email outbox; secrets and OTPs are never logged.

Delivery is at least once. A retry may deliver the same still-valid code twice;
verification remains single-use and only the current challenge is accepted.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models import EmailOutbox, EmailVerification, User
from app.smtp_transport import deliver_confirmation, email_configured


async def process_email_outbox(batch_size: int = 50) -> dict:
    if not email_configured():
        return {'sent': 0, 'failed': 0, 'configured': False}
    engine = create_async_engine(settings().database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    sent = failed = 0
    try:
        async with sessions() as db:
            due = list((await db.execute(select(EmailOutbox.id, EmailOutbox.user_id).where(
                EmailOutbox.status == 'pending', EmailOutbox.next_attempt_at <= datetime.now(timezone.utc)
            ).order_by(EmailOutbox.next_attempt_at, EmailOutbox.id).limit(max(1, min(batch_size, 100))))).all())
        for outbox_id, user_id in due:
            async with sessions.begin() as db:
                # Same lock ordering as verify/resend/delete-account prevents races.
                user = await db.scalar(select(User).where(User.id == user_id).with_for_update(skip_locked=True))
                if not user:
                    continue
                item = await db.get(EmailOutbox, outbox_id, with_for_update=True)
                if not item or item.status != 'pending' or item.next_attempt_at > datetime.now(timezone.utc):
                    continue
                challenge = await db.get(EmailVerification, user_id)
                now = datetime.now(timezone.utc)
                if user.email_verified or not challenge or challenge.version != item.verification_version or challenge.expires_at <= now:
                    item.status = 'cancelled'
                    item.code_encrypted = ''
                    continue
                item.attempts += 1
                try:
                    code = Fernet(settings().data_key.get_secret_value().encode()).decrypt(item.code_encrypted.encode()).decode()
                    await asyncio.to_thread(deliver_confirmation, user.email, code)
                except Exception:
                    # Never return/log SMTP exception text: providers may echo PII.
                    failed += 1
                    if item.attempts >= 5:
                        item.status = 'failed'
                        item.code_encrypted = ''
                    else:
                        item.next_attempt_at = now + timedelta(seconds=min(15 * 2 ** item.attempts, 240))
                    continue
                item.status = 'sent'
                item.delivered_at = datetime.now(timezone.utc)
                item.code_encrypted = ''
                sent += 1
        return {'sent': sent, 'failed': failed, 'configured': True}
    finally:
        await engine.dispose()
