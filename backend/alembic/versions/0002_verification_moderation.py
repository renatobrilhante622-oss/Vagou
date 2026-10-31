"""Email verification, corporate registration and job moderation.

Existing and new accounts require confirmation; existing ads stay approved during rollout.
New ads enter moderation. No account is marked verified without an OTP confirmation.
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('email_verified', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('users', sa.Column('company_cnpj', sa.String(14), nullable=True))
    op.add_column('users', sa.Column('company_name', sa.String(200), nullable=True))
    op.add_column('users', sa.Column('company_contact_email', sa.String(254), nullable=True))
    op.create_unique_constraint('uq_users_company_cnpj', 'users', ['company_cnpj'])
    op.alter_column('jobs', 'recruiter_id', nullable=True)
    op.add_column('jobs', sa.Column('moderation_status', sa.String(16), nullable=False, server_default='approved'))
    op.alter_column('jobs', 'moderation_status', server_default='pending')
    op.create_index('ix_jobs_moderation_status', 'jobs', ['moderation_status'])
    op.create_check_constraint('ck_job_moderation_status', 'jobs', "moderation_status IN ('pending','approved','rejected')")
    op.add_column('jobs', sa.Column('moderation_note', sa.String(1000), nullable=True))
    op.add_column('jobs', sa.Column('moderated_by', sa.Uuid(), nullable=True))
    op.add_column('jobs', sa.Column('moderated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('jobs', sa.Column('source_url', sa.Text(), nullable=True))
    op.add_column('jobs', sa.Column('source_external_id', sa.String(255), nullable=True))
    op.add_column('jobs', sa.Column('source_name', sa.String(120), nullable=False, server_default='Vagou!'))
    op.create_unique_constraint('uq_job_source_external_id', 'jobs', ['source_name', 'source_external_id'])
    op.create_table('email_verifications',
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('version', sa.Uuid(), nullable=False),
        sa.Column('code_digest', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False))
    op.create_table('email_outbox',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('verification_version', sa.Uuid(), nullable=False),
        sa.Column('code_encrypted', sa.Text(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending','sent','cancelled','failed')", name='ck_email_outbox_status'))
    op.create_index('ix_email_outbox_user_id', 'email_outbox', ['user_id'])
    op.create_index('ix_email_outbox_status', 'email_outbox', ['status'])


def downgrade():
    op.drop_table('email_outbox')
    op.drop_table('email_verifications')
    op.drop_constraint('uq_job_source_external_id', 'jobs', type_='unique')
    for name in ['source_name', 'source_external_id', 'source_url', 'moderated_at', 'moderated_by', 'moderation_note']:
        op.drop_column('jobs', name)
    op.drop_constraint('ck_job_moderation_status', 'jobs', type_='check')
    op.drop_index('ix_jobs_moderation_status', table_name='jobs')
    op.drop_column('jobs', 'moderation_status')
    # External catalog rows have no recruiter and cannot exist in the old schema.
    op.execute(sa.text('DELETE FROM jobs WHERE recruiter_id IS NULL'))
    op.alter_column('jobs', 'recruiter_id', nullable=False)
    op.drop_constraint('uq_users_company_cnpj', 'users', type_='unique')
    for name in ['company_contact_email', 'company_name', 'company_cnpj', 'email_verified']:
        op.drop_column('users', name)
