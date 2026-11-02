"""add grocery session idempotency keys

Revision ID: a4d9c69b8f21
Revises: 17b3f362987d
Create Date: 2026-10-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4d9c69b8f21"
down_revision: Union[str, Sequence[str], None] = "17b3f362987d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("grocery_sessions", sa.Column("idempotency_key", sa.String(length=36), nullable=True))
    op.add_column("grocery_sessions", sa.Column("idempotency_fingerprint", sa.String(length=64), nullable=True))
    op.create_index("ix_grocery_sessions_idempotency_key", "grocery_sessions", ["idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_grocery_sessions_idempotency_key", table_name="grocery_sessions")
    op.drop_column("grocery_sessions", "idempotency_fingerprint")
    op.drop_column("grocery_sessions", "idempotency_key")
