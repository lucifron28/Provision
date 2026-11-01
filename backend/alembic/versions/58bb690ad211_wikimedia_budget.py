"""Add the Wikimedia request budget.

Revision ID: 58bb690ad211
Revises: f56c9a214e0b
"""
from alembic import op
import sqlalchemy as sa

revision = "58bb690ad211"
down_revision = "f56c9a214e0b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "wikimedia_budget",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("used", sa.Integer(), nullable=False),
        sa.Column("next_allowed", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_wikimedia_budget_singleton"),
    )


def downgrade():
    used = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM wikimedia_budget WHERE used > 0 OR paused"
    )).scalar_one()
    if used:
        raise RuntimeError("Wikimedia request budget history would be lost")
    op.drop_table("wikimedia_budget")
