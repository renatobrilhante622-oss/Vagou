"""Reconcile the status timestamp index across prior 0004 installations."""
from alembic import op

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    # Some installations ran 0004 before its index statement was removed.
    op.create_index('ix_applications_status_updated_at', 'applications',
                    ['status_updated_at'], if_not_exists=True)


def downgrade():
    op.drop_index('ix_applications_status_updated_at', table_name='applications',
                  if_exists=True)
