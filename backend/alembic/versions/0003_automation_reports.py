"""Premium automation execution reports."""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('automation_runs',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('candidate_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True)),
        sa.Column('scanned_jobs', sa.Integer(), nullable=False),
        sa.Column('eligible_jobs', sa.Integer(), nullable=False),
        sa.Column('submitted_applications', sa.Integer(), nullable=False),
        sa.Column('manual_review_jobs', sa.Integer(), nullable=False),
        sa.Column('error_count', sa.Integer(), nullable=False),
        sa.Column('omitted_events', sa.Integer(), nullable=False),
        sa.CheckConstraint("status IN ('running','complete','failed')", name='ck_automation_run_status'))
    op.create_index('ix_automation_runs_candidate_id', 'automation_runs', ['candidate_id'])
    op.create_index('ix_automation_runs_started_at', 'automation_runs', ['started_at'])
    op.create_table('automation_events',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('run_id', sa.Uuid(), sa.ForeignKey('automation_runs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('job_id', sa.Uuid(), sa.ForeignKey('jobs.id', ondelete='SET NULL')),
        sa.Column('job_title', sa.String(160)),
        sa.Column('job_url', sa.Text()),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('detail', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('submitted','already_applied','requires_manual','missing_resume','failed')", name='ck_automation_event_status'))
    op.create_index('ix_automation_events_run_id', 'automation_events', ['run_id'])


def downgrade():
    op.drop_table('automation_events')
    op.drop_table('automation_runs')
