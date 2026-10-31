"""Add optional contract type to vacancies."""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('jobs', sa.Column('contract_type', sa.String(16), nullable=True))


def downgrade():
    op.drop_column('jobs', 'contract_type')