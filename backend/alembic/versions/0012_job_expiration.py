"""Keep the publisher's expiration for truthful catalog cleanup."""

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "jobs", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade():
    op.drop_column("jobs", "expires_at")
