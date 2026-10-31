"""Initial schema; explicit immutable migration independent of application models."""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('users',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('email', sa.String(254), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('role', sa.String(16), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('phone_encrypted', sa.Text()),
        sa.Column('skills', sa.JSON(), nullable=False),
        sa.Column('preferences', sa.JSON(), nullable=False),
        sa.Column('is_premium', sa.Boolean(), nullable=False),
        sa.Column('automation_enabled', sa.Boolean(), nullable=False),
        sa.Column('resume_key', sa.String(64)),
        sa.Column('token_version', sa.Integer(), nullable=False),
        sa.Column('privacy_version', sa.String(32), nullable=False),
        sa.Column('consent_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('candidate','recruiter')"))
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_table('jobs',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('recruiter_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(160), nullable=False),
        sa.Column('company', sa.String(160), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('salary_min', sa.Numeric(12, 2), nullable=False),
        sa.Column('salary_max', sa.Numeric(12, 2), nullable=False),
        sa.Column('modality', sa.String(16), nullable=False),
        sa.Column('location', sa.String(160), nullable=False),
        sa.Column('keywords', sa.JSON(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('salary_min >= 0 AND salary_max >= salary_min'),
        sa.CheckConstraint("modality IN ('remote','hybrid','onsite')"))
    op.create_index('ix_jobs_recruiter_id', 'jobs', ['recruiter_id'])
    op.create_index('ix_jobs_created_at', 'jobs', ['created_at'])
    op.create_table('applications',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('candidate_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('job_id', sa.Uuid(), sa.ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('source', sa.String(16), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('match_score', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('candidate_id', 'job_id', name='uq_application_candidate_job'),
        sa.CheckConstraint("source IN ('manual','automatic')"),
        sa.CheckConstraint("status IN ('submitted','reviewing','interview','rejected','hired')"),
        sa.CheckConstraint('match_score BETWEEN 0 AND 100'))
    op.create_index('ix_applications_candidate_id', 'applications', ['candidate_id'])
    op.create_index('ix_applications_job_id', 'applications', ['job_id'])


def downgrade():
    op.drop_table('applications')
    op.drop_table('jobs')
    op.drop_table('users')