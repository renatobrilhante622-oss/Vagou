"""Durable staff notices, encrypted at rest and sent only after commit."""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.models import SystemNotification, User
from app.config import settings
from app.security import cipher
from app.smtp_transport import email_configured, send_transactional_message

logger = logging.getLogger(__name__)


async def queue_notice(db, user_id, subject, body):
    db.add(
        SystemNotification(
            user_id=user_id,
            payload_encrypted=cipher()
            .encrypt(
                json.dumps(
                    {"subject": subject, "body": body}, ensure_ascii=False
                ).encode()
            )
            .decode(),
        )
    )


async def process_notices():
    if not email_configured():
        return {"sent": 0, "configured": False}
    engine = create_async_engine(settings().database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    sent = 0
    try:
        async with sessions.begin() as db:
            rows = (
                await db.scalars(
                    select(SystemNotification)
                    .where(
                        SystemNotification.status == "pending",
                        SystemNotification.next_attempt_at
                        <= datetime.now(timezone.utc),
                    )
                    .order_by(SystemNotification.created_at)
                    .limit(30)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for row in rows:
                user = await db.get(User, row.user_id)
                if not user or not user.email_verified or not user.is_active:
                    row.status = "cancelled"
                    row.payload_encrypted = ""
                    continue
                row.attempts += 1
                try:
                    data = json.loads(cipher().decrypt(row.payload_encrypted.encode()))
                    message = EmailMessage()
                    message["From"] = settings().smtp_from
                    message["To"] = user.email
                    message["Subject"] = " ".join(data["subject"].split())[:160]
                    message["Message-ID"] = (
                        f"<notice-{row.id}@notifications.vagou.invalid>"
                    )
                    message.set_content(data["body"])
                    await asyncio.to_thread(send_transactional_message, message)
                except Exception as error:
                    logger.error(
                        "system_notice_failed id=%s error_type=%s",
                        row.id,
                        type(error).__name__,
                    )
                    if row.attempts >= 5:
                        row.status = "failed"
                        row.payload_encrypted = ""
                    else:
                        row.next_attempt_at = datetime.now(timezone.utc) + timedelta(
                            seconds=60 * 2**row.attempts
                        )
                else:
                    sent += 1
                    row.status = "sent"
                    row.payload_encrypted = ""
        return {"sent": sent, "configured": True}
    finally:
        await engine.dispose()
