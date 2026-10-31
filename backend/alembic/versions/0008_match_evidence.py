"""Persist source snapshots and explainable automation match categories."""
from alembic import op
import sqlalchemy as sa

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('automation_runs', sa.Column('collected_jobs', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('automation_runs', sa.Column('external_jobs_scanned', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('automation_runs', sa.Column('possible_match_jobs', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('automation_events', sa.Column('company', sa.String(160)))
    op.add_column('automation_events', sa.Column('location', sa.String(160)))
    op.add_column('automation_events', sa.Column('source_name', sa.String(120)))
    op.add_column('automation_events', sa.Column('match_score', sa.Integer()))
    op.add_column('automation_events', sa.Column('match_reasons', sa.JSON()))
    op.drop_constraint('ck_automation_event_status', 'automation_events', type_='check')
    op.create_check_constraint('ck_automation_event_status', 'automation_events',
        "status IN ('submitted','already_applied','requires_manual','possible_match','missing_resume','filtered','failed')")


def downgrade():
    op.execute("UPDATE automation_events SET status = 'requires_manual' WHERE status = 'possible_match'")
    op.drop_constraint('ck_automation_event_status', 'automation_events', type_='check')
    op.create_check_constraint('ck_automation_event_status', 'automation_events',
        "status IN ('submitted','already_applied','requires_manual','missing_resume','filtered','failed')")
    for column in ('match_reasons', 'match_score', 'source_name', 'location', 'company'):
        op.drop_column('automation_events', column)
    op.drop_column('automation_runs', 'possible_match_jobs')
    op.drop_column('automation_runs', 'external_jobs_scanned')
    op.drop_column('automation_runs', 'collected_jobs')