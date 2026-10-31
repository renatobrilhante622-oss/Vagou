"""Private audit records for premium automation, removed with account deletion."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AutomationRun(Base):
    __tablename__ = 'automation_runs'
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    status: Mapped[str] = mapped_column(String(16), default='running')
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scanned_jobs: Mapped[int] = mapped_column(Integer, default=0)
    eligible_jobs: Mapped[int] = mapped_column(Integer, default=0)
    submitted_applications: Mapped[int] = mapped_column(Integer, default=0)
    manual_review_jobs: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    omitted_events: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (CheckConstraint("status IN ('running','complete','failed')", name='ck_automation_run_status'),)


class AutomationEvent(Base):
    __tablename__ = 'automation_events'
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('automation_runs.id', ondelete='CASCADE'), index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('jobs.id', ondelete='SET NULL'))
    # Snapshot public vacancy metadata; never copy applicant PII or resume bytes.
    job_title: Mapped[str | None] = mapped_column(String(160))
    job_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24))
    detail: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (CheckConstraint("status IN ('submitted','already_applied','requires_manual','missing_resume','failed','limit_reached','criteria_missing')", name='ck_automation_event_status'),)
