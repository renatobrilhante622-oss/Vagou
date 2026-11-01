"""Staff roles, audited administration and encrypted candidate dossiers."""

from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    for constraint in sa.inspect(op.get_bind()).get_check_constraints("users"):
        if "role" in constraint["sqltext"]:
            op.drop_constraint(constraint["name"], "users", type_="check")
    op.create_check_constraint(
        "ck_user_role",
        "users",
        "role IN ('candidate','recruiter','moderator','super_admin')",
    )
    for column in [
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "company_verified", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("birth_date", sa.Date()),
        sa.Column("cpf_encrypted", sa.Text()),
        sa.Column("seniority", sa.String(32)),
        sa.Column("linkedin_url", sa.Text()),
        sa.Column("professional_summary", sa.Text()),
        sa.Column("candidate_city", sa.String(80)),
        sa.Column("candidate_state", sa.String(2)),
        sa.Column("desired_salary", sa.Numeric(12, 2)),
    ]:
        op.add_column("users", column)
    op.add_column(
        "jobs",
        sa.Column("featured", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        sa.text(
            "UPDATE users SET role='super_admin',is_premium=true,is_active=true WHERE lower(email)='rbrilhante001@gmail.com'"
        )
    )
    op.create_table(
        "admin_audits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.Uuid()),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_admin_audits_actor_id", "admin_audits", ["actor_id"])
    op.create_index("ix_admin_audits_created_at", "admin_audits", ["created_at"])
    op.create_table(
        "system_notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("payload_encrypted", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('pending','sent','failed','cancelled')",
            name="ck_system_notification_status",
        ),
    )
    op.create_index(
        "ix_system_notifications_user_id", "system_notifications", ["user_id"]
    )
    op.create_index(
        "ix_system_notifications_status", "system_notifications", ["status"]
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT count(*) FROM users WHERE role IN ('super_admin','moderator')")
    ):
        raise RuntimeError("Resolve staff assignments before downgrading.")
    op.drop_table("system_notifications")
    op.drop_table("admin_audits")
    op.drop_column("jobs", "featured")
    for name in [
        "desired_salary",
        "candidate_state",
        "candidate_city",
        "professional_summary",
        "linkedin_url",
        "seniority",
        "cpf_encrypted",
        "birth_date",
        "company_verified",
        "is_active",
    ]:
        op.drop_column("users", name)
    op.drop_constraint("ck_user_role", "users", type_="check")
    op.create_check_constraint(
        "users_role_check", "users", "role IN ('candidate','recruiter')"
    )
