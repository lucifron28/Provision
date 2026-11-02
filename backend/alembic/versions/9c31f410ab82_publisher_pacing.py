"""Add durable publisher-specific request pacing.

Revision ID: 9c31f410ab82
Revises: 7ac91de48236
"""
from alembic import op
import sqlalchemy as sa

revision = "9c31f410ab82"
down_revision = "7ac91de48236"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "publisher_pacing",
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("recipe_sources.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("window_started", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_used", sa.Integer(), nullable=False),
        sa.Column("next_allowed", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False),
    )


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM publisher_pacing")).scalar_one():
        raise RuntimeError("Publisher pacing history would be lost")
    op.drop_table("publisher_pacing")
