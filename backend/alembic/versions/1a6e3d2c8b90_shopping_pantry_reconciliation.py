"""Add reviewed purchased-to-pantry reconciliation.

Revision ID: 1a6e3d2c8b90
Revises: 0b3f9a71c8d2
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "1a6e3d2c8b90"
down_revision = "0b3f9a71c8d2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "shopping_list_items",
        sa.Column("reconciliation_status", sa.String(length=24), server_default="pending", nullable=False),
    )
    op.create_check_constraint(
        "ck_shopping_items_reconciliation_status",
        "shopping_list_items",
        "reconciliation_status IN ('pending', 'added_to_pantry', 'excluded')",
    )
    op.create_table(
        "shopping_pantry_reconciliation_idempotency",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "length(idempotency_key) BETWEEN 8 AND 128",
            name="ck_shopping_pantry_reconcile_key_length",
        ),
        sa.CheckConstraint("length(request_hash) = 64", name="ck_shopping_pantry_reconcile_request_hash"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "household_id", "idempotency_key", name="uq_shopping_pantry_reconcile_household_key"
        ),
    )
    op.create_index(
        op.f("ix_shopping_pantry_reconciliation_idempotency_household_id"),
        "shopping_pantry_reconciliation_idempotency",
        ["household_id"],
        unique=False,
    )


def downgrade():
    reconciled = op.get_bind().execute(
        sa.text("SELECT count(*) FROM shopping_list_items WHERE reconciliation_status <> 'pending'")
    ).scalar_one()
    recorded = op.get_bind().execute(
        sa.text("SELECT count(*) FROM shopping_pantry_reconciliation_idempotency")
    ).scalar_one()
    if reconciled or recorded:
        raise RuntimeError("Purchased-to-pantry reconciliation history would be lost")
    op.drop_index(
        op.f("ix_shopping_pantry_reconciliation_idempotency_household_id"),
        table_name="shopping_pantry_reconciliation_idempotency",
    )
    op.drop_table("shopping_pantry_reconciliation_idempotency")
    op.drop_constraint("ck_shopping_items_reconciliation_status", "shopping_list_items", type_="check")
    op.drop_column("shopping_list_items", "reconciliation_status")
