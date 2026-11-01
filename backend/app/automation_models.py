"""Private audit records for premium automation, removed with account deletion."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AutomationRun(Base):
    __tablename__ = 'automation_runs'
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    status: Mapped[str] = mapped_column(String(16), default='running')
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_jobs: Mapped[int] = mapped_column(Integer, default=0)
    consent_granted: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    search_channels_count: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    scanned_jobs: Mapped[int] = mapped_column(Integer, default=0)
    external_jobs_scanned: Mapped[int] = mapped_column(Integer, default=0)
    filtered_jobs: Mapped[int] = mapped_column(Integer, default=0)
    possible_match_jobs: Mapped[int] = mapped_column(Integer, default=0)
    eligible_jobs: Mapped[int] = mapped_column(Integer, default=0)
    submitted_applications: Mapped[int] = mapped_column(Integer, default=0)
    manual_review_jobs: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    omitted_events: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (CheckConstraint("status IN ('queued','running','complete','failed','cancelled')", name='ck_automation_run_status'),)


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
    company: Mapped[str | None] = mapped_column(String(160))
    location: Mapped[str | None] = mapped_column(String(160))
    source_name: Mapped[str | None] = mapped_column(String(120))
    match_score: Mapped[int | None] = mapped_column(Integer)
    match_reasons: Mapped[list | None] = mapped_column(JSON)
    destination_channel: Mapped[str | None] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(String(254))
    city: Mapped[str | None] = mapped_column(String(80))
    state: Mapped[str | None] = mapped_column(String(2))
    modality: Mapped[str | None] = mapped_column(String(16))
    contract_type: Mapped[str | None] = mapped_column(String(16))
    salary_min: Mapped[float | None] = mapped_column(Numeric(12, 2))
    salary_max: Mapped[float | None] = mapped_column(Numeric(12, 2))
    __table_args__ = (CheckConstraint("status IN ('submitted','already_applied','requires_manual','possible_match','missing_resume','filtered','failed','limit_reached','search_channel')", name='ck_automation_event_status'),)
