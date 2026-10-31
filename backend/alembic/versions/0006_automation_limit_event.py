"""Record eligible applications deferred by the candidate's per-cycle limit."""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('ck_automation_event_status', 'automation_events', type_='check')
    op.create_check_constraint('ck_automation_event_status', 'automation_events',
        "status IN ('submitted','already_applied','requires_manual','missing_resume','failed','limit_reached','criteria_missing')")


def downgrade():
    op.execute(sa.text("UPDATE automation_events SET status='requires_manual' WHERE status IN ('limit_reached','criteria_missing')"))
    op.drop_constraint('ck_automation_event_status', 'automation_events', type_='check')
    op.create_check_constraint('ck_automation_event_status', 'automation_events',
        "status IN ('submitted','already_applied','requires_manual','missing_resume','failed')")
