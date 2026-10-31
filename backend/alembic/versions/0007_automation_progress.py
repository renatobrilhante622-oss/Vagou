"""Track queued runs and filtered opportunities."""
from alembic import op
import sqlalchemy as sa

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('automation_runs', sa.Column('filtered_jobs', sa.Integer(), nullable=False, server_default='0'))
    op.drop_constraint('ck_automation_run_status', 'automation_runs', type_='check')
    op.create_check_constraint('ck_automation_run_status', 'automation_runs',
        "status IN ('queued','running','complete','failed','cancelled')")
    op.drop_constraint('ck_automation_event_status', 'automation_events', type_='check')
    op.create_check_constraint('ck_automation_event_status', 'automation_events',
        "status IN ('submitted','already_applied','requires_manual','missing_resume','filtered','failed')")


def downgrade():
    op.execute("UPDATE automation_runs SET status = 'failed' WHERE status IN ('queued','cancelled')")
    op.execute("UPDATE automation_events SET status = 'failed' WHERE status = 'filtered'")
    op.drop_constraint('ck_automation_event_status', 'automation_events', type_='check')
    op.create_check_constraint('ck_automation_event_status', 'automation_events',
        "status IN ('submitted','already_applied','requires_manual','missing_resume','failed')")
    op.drop_constraint('ck_automation_run_status', 'automation_runs', type_='check')
    op.create_check_constraint('ck_automation_run_status', 'automation_runs',
        "status IN ('running','complete','failed')")
    op.drop_column('automation_runs', 'filtered_jobs')