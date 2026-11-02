"""Add shared DeepSeek request budget.

Revision ID: b561d1e948a7
Revises: f19c02a6e4b7
"""

from alembic import op
import sqlalchemy as sa

revision = "b561d1e948a7"
down_revision = "f19c02a6e4b7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "deepseek_budget",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("used", sa.Integer(), nullable=False),
        sa.Column("window_used", sa.Integer(), nullable=False),
        sa.Column("window_started", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    used = op.get_bind().execute(sa.text("SELECT count(*) FROM deepseek_budget WHERE used > 0")).scalar_one()
    if used:
        raise RuntimeError("DeepSeek request budget history would be lost")
    op.drop_table("deepseek_budget")
