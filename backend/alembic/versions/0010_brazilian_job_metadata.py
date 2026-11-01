"""Structured Brazilian locations and durable rich vacancy report snapshots."""
from alembic import op
import sqlalchemy as sa

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade():
    # Nullable additions preserve existing vacancies and historical applications.
    op.add_column('jobs', sa.Column('city', sa.String(80)))
    op.add_column('jobs', sa.Column('state', sa.String(2)))
    op.add_column('jobs', sa.Column('country', sa.String(2)))
    for column in [
        sa.Column('description', sa.Text()),
        sa.Column('contact_email', sa.String(254)),
        sa.Column('city', sa.String(80)),
        sa.Column('state', sa.String(2)),
        sa.Column('modality', sa.String(16)),
        sa.Column('contract_type', sa.String(16)),
        sa.Column('salary_min', sa.Numeric(12, 2)),
        sa.Column('salary_max', sa.Numeric(12, 2)),
    ]:
        op.add_column('automation_events', column)


def downgrade():
    for name in ('salary_max', 'salary_min', 'contract_type', 'modality',
                 'state', 'city', 'contact_email', 'description'):
        op.drop_column('automation_events', name)
    for name in ('country', 'state', 'city'):
        op.drop_column('jobs', name)
