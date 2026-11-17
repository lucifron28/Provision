from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class InventoryActionIdempotency(Base, TimestampMixin):
    """Persist a stock-action result so exact retries cannot repeat mutations."""

    __tablename__ = "inventory_action_idempotency"
    __table_args__ = (
        UniqueConstraint("household_id", "idempotency_key", name="uq_inventory_action_household_key"),
        CheckConstraint("action_type IN ('consume', 'discard', 'adjust')", name="ck_inventory_action_type"),
        CheckConstraint("length(idempotency_key) BETWEEN 8 AND 128", name="ck_inventory_action_key_length"),
        CheckConstraint("length(request_hash) = 64", name="ck_inventory_action_request_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action_type: Mapped[str] = mapped_column(String(24), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
