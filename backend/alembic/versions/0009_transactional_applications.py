"""Transactional application emails and explicit destination metadata."""
from alembic import op
import sqlalchemy as sa

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('jobs', sa.Column('contact_email', sa.String(254)))
    op.add_column('applications', sa.Column('delivery_status', sa.String(24), nullable=False, server_default='not_requested'))
    op.add_column('applications', sa.Column('destination_channel', sa.String(32)))
    # The original application status check was unnamed in migration 0001.
    for constraint in sa.inspect(op.get_bind()).get_check_constraints('applications'):
        if 'status' in constraint['sqltext']:
            op.drop_constraint(constraint['name'], 'applications', type_='check')
    op.create_check_constraint('ck_application_status', 'applications',
        "status IN ('submitted','reviewing','interview','rejected','hired','requires_manual')")
    op.add_column('automation_runs', sa.Column('consent_granted', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('automation_runs', sa.Column('search_channels_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('automation_events', sa.Column('destination_channel', sa.String(32)))
    op.drop_constraint('ck_automation_event_status', 'automation_events', type_='check')
    op.create_check_constraint('ck_automation_event_status', 'automation_events',
        "status IN ('submitted','already_applied','requires_manual','possible_match','missing_resume','filtered','failed','limit_reached','search_channel')")
    op.create_table('application_notifications',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('application_id', sa.Uuid(), sa.ForeignKey('applications.id', ondelete='CASCADE')),
        sa.Column('run_id', sa.Uuid(), sa.ForeignKey('automation_runs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('recipient_encrypted', sa.Text(), nullable=False),
        sa.Column('payload_encrypted', sa.Text(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('delivered_at', sa.DateTime(timezone=True)),
        sa.Column('dedup_key', sa.String(255), nullable=False),
        sa.UniqueConstraint('dedup_key', name='uq_application_notifications_dedup'),
        sa.CheckConstraint("status IN ('pending','sent','failed','cancelled')", name='ck_application_notification_status'))
    for column in ['user_id', 'run_id', 'status']:
        op.create_index('ix_application_notifications_' + column, 'application_notifications', [column])


def downgrade():
    manual = op.get_bind().scalar(sa.text("SELECT count(*) FROM applications WHERE status='requires_manual'"))
    if manual:
        raise RuntimeError('Export or resolve pending manual applications before downgrading; the old schema cannot represent them.')
    op.drop_table('application_notifications')
    op.execute(sa.text("UPDATE automation_events SET status='requires_manual' WHERE status IN ('search_channel','limit_reached')"))
    op.drop_constraint('ck_automation_event_status', 'automation_events', type_='check')
    op.create_check_constraint('ck_automation_event_status', 'automation_events',
        "status IN ('submitted','already_applied','requires_manual','possible_match','missing_resume','filtered','failed')")
    op.drop_column('automation_events', 'destination_channel')
    op.drop_column('automation_runs', 'search_channels_count')
    op.drop_column('automation_runs', 'consent_granted')
    op.drop_constraint('ck_application_status', 'applications', type_='check')
    op.create_check_constraint('applications_status_check', 'applications', "status IN ('submitted','reviewing','interview','rejected','hired')")
    op.drop_column('applications', 'destination_channel')
    op.drop_column('applications', 'delivery_status')
    op.drop_column('jobs', 'contact_email')
