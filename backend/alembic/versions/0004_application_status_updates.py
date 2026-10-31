"""Timestamp status changes so candidates can see fresh updates."""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('applications', sa.Column('status_updated_at', sa.DateTime(timezone=True),
                                            nullable=False, server_default=sa.func.now()))
    op.create_index('ix_applications_status_updated_at', 'applications', ['status_updated_at'])


def downgrade():
    op.drop_index('ix_applications_status_updated_at', table_name='applications')
    op.drop_column('applications', 'status_updated_at')
