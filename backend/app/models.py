import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = 'users'
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    company_cnpj: Mapped[str | None] = mapped_column(String(14))
    company_name: Mapped[str | None] = mapped_column(String(200))
    company_contact_email: Mapped[str | None] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(120))
    phone_encrypted: Mapped[str | None] = mapped_column(Text)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    automation_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    resume_key: Mapped[str | None] = mapped_column(String(64))
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    privacy_version: Mapped[str] = mapped_column(String(32))
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint("role IN ('candidate','recruiter')"),
        UniqueConstraint('company_cnpj', name='uq_users_company_cnpj'),
    )


class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    recruiter_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(160))
    company: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    salary_min: Mapped[float] = mapped_column(Numeric(12, 2))
    salary_max: Mapped[float] = mapped_column(Numeric(12, 2))
    modality: Mapped[str] = mapped_column(String(16))
    contract_type: Mapped[str | None] = mapped_column(String(16))
    location: Mapped[str] = mapped_column(String(160))
    city: Mapped[str | None] = mapped_column(String(80))
    state: Mapped[str | None] = mapped_column(String(2))
    country: Mapped[str | None] = mapped_column(String(2))
    keywords: Mapped[list] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    moderation_status: Mapped[str] = mapped_column(String(16), default='pending', server_default='pending', index=True)
    moderation_note: Mapped[str | None] = mapped_column(String(1000))
    moderated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_url: Mapped[str | None] = mapped_column(Text)
    source_external_id: Mapped[str | None] = mapped_column(String(255))
    source_name: Mapped[str] = mapped_column(String(120), default='Vagou!', server_default='Vagou!')
    contact_email: Mapped[str | None] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    __table_args__ = (
        CheckConstraint('salary_min >= 0 AND salary_max >= salary_min'),
        UniqueConstraint('source_name', 'source_external_id', name='uq_job_source_external_id'),
        CheckConstraint("moderation_status IN ('pending','approved','rejected')", name='ck_job_moderation_status'),
        CheckConstraint("modality IN ('remote','hybrid','onsite')"),
    )

    @property
    def company_name(self) -> str:
        return self.company

    @property
    def external_url(self) -> str | None:
        return self.source_url

    @property
    def recruiter_email(self) -> str | None:
        return self.contact_email

    @property
    def modality_label(self) -> str:
        return {'remote': 'Remoto', 'hybrid': 'Híbrido', 'onsite': 'Presencial'}.get(self.modality, self.modality)


class Application(Base):
    __tablename__ = 'applications'
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('jobs.id', ondelete='CASCADE'), index=True)
    source: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), default='submitted')
    match_score: Mapped[int] = mapped_column(Integer)
    delivery_status: Mapped[str] = mapped_column(String(24), default='not_requested', server_default='not_requested')
    destination_channel: Mapped[str | None] = mapped_column(String(32))
    status_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint('candidate_id', 'job_id', name='uq_application_candidate_job'),
        CheckConstraint("source IN ('manual','automatic')"),
        CheckConstraint("status IN ('submitted','reviewing','interview','rejected','hired','requires_manual')", name='ck_application_status'),
        CheckConstraint('match_score BETWEEN 0 AND 100'),
    )


class EmailVerification(Base):
    __tablename__ = 'email_verifications'
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    version: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    code_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class EmailOutbox(Base):
    __tablename__ = 'email_outbox'
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    verification_version: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    code_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default='pending', index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("status IN ('pending','sent','cancelled','failed')", name='ck_email_outbox_status'),)


class ApplicationNotification(Base):
    __tablename__ = 'application_notifications'
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('applications.id', ondelete='CASCADE'))
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('automation_runs.id', ondelete='CASCADE'), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    recipient_encrypted: Mapped[str] = mapped_column(Text)
    payload_encrypted: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default='pending', index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dedup_key: Mapped[str] = mapped_column(String(255))
    __table_args__ = (
        UniqueConstraint('dedup_key', name='uq_application_notifications_dedup'),
        CheckConstraint("status IN ('pending','sent','failed','cancelled')", name='ck_application_notification_status'),
    )
