"""Persist exact manual inventory intake retries.

Revision ID: 0b3f9a71c8d2
Revises: 9c31f410ab82
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0b3f9a71c8d2"
down_revision = "9c31f410ab82"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "manual_inventory_intake_idempotency",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("length(idempotency_key) BETWEEN 8 AND 128", name="ck_manual_intake_key_length"),
        sa.CheckConstraint("length(request_hash) = 64", name="ck_manual_intake_request_hash"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("household_id", "idempotency_key", name="uq_manual_intake_household_key"),
    )
    op.create_index(
        op.f("ix_manual_inventory_intake_idempotency_household_id"),
        "manual_inventory_intake_idempotency",
        ["household_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_manual_inventory_intake_idempotency_household_id"),
        table_name="manual_inventory_intake_idempotency",
    )
    op.drop_table("manual_inventory_intake_idempotency")
