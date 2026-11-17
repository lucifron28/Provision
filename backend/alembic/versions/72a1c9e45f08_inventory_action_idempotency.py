"""Store idempotent stock-action responses.

Revision ID: 72a1c9e45f08
Revises: 1a6e3d2c8b90
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "72a1c9e45f08"
down_revision = "1a6e3d2c8b90"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventory_action_idempotency",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("action_type", sa.String(length=24), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "action_type IN ('consume', 'discard', 'adjust')", name="ck_inventory_action_type"
        ),
        sa.CheckConstraint(
            "length(idempotency_key) BETWEEN 8 AND 128", name="ck_inventory_action_key_length"
        ),
        sa.CheckConstraint("length(request_hash) = 64", name="ck_inventory_action_request_hash"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("household_id", "idempotency_key", name="uq_inventory_action_household_key"),
    )
    op.create_index(
        op.f("ix_inventory_action_idempotency_household_id"),
        "inventory_action_idempotency",
        ["household_id"],
        unique=False,
    )


def downgrade():
    recorded = op.get_bind().execute(
        sa.text("SELECT count(*) FROM inventory_action_idempotency")
    ).scalar_one()
    if recorded:
        raise RuntimeError("Inventory action retry history would be lost")
    op.drop_index(
        op.f("ix_inventory_action_idempotency_household_id"),
        table_name="inventory_action_idempotency",
    )
    op.drop_table("inventory_action_idempotency")
