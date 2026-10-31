"""Add a durable TheMealDB request budget.

Revision ID: f56c9a214e0b
Revises: e732bb5a4691
"""

from alembic import op
import sqlalchemy as sa

revision = "f56c9a214e0b"
down_revision = "e732bb5a4691"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "themealdb_budget",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("used", sa.Integer(), nullable=False),
        sa.Column("next_allowed", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_themealdb_budget_singleton"),
    )


def downgrade():
    used = op.get_bind().execute(sa.text("SELECT count(*) FROM themealdb_budget WHERE used > 0 OR paused")).scalar_one()
    if used:
        raise RuntimeError("TheMealDB request budget history would be lost")
    op.drop_table("themealdb_budget")
