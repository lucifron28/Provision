"""Add a durable publisher fetch budget.

Revision ID: 7ac91de48236
Revises: 58bb690ad211
"""
from alembic import op
import sqlalchemy as sa

revision = "7ac91de48236"
down_revision = "58bb690ad211"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("publisher_budget",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("used", sa.Integer(), nullable=False),
        sa.Column("window_started", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_publisher_budget_singleton"))


def downgrade():
    used = op.get_bind().execute(sa.text("SELECT count(*) FROM publisher_budget WHERE used > 0")).scalar_one()
    if used:
        raise RuntimeError("Publisher request budget history would be lost")
    op.drop_table("publisher_budget")
