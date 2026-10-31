"""Add a request budget for each household.

Revision ID: e732bb5a4691
Revises: b561d1e948a7
"""

from alembic import op
import sqlalchemy as sa

revision = "e732bb5a4691"
down_revision = "b561d1e948a7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "household_deepseek_budget",
        sa.Column("household_id", sa.Integer(), sa.ForeignKey("households.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("used", sa.Integer(), nullable=False),
    )


def downgrade():
    used = op.get_bind().execute(sa.text("SELECT count(*) FROM household_deepseek_budget WHERE used > 0")).scalar_one()
    if used:
        raise RuntimeError("Household DeepSeek request budget history would be lost")
    op.drop_table("household_deepseek_budget")
