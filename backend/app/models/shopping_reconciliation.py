from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ShoppingPantryReconciliationIdempotency(Base, TimestampMixin):
    """Persist an exact purchased-to-pantry confirmation result."""

    __tablename__ = "shopping_pantry_reconciliation_idempotency"
    __table_args__ = (
        UniqueConstraint(
            "household_id", "idempotency_key", name="uq_shopping_pantry_reconcile_household_key"
        ),
        CheckConstraint("length(idempotency_key) BETWEEN 8 AND 128", name="ck_shopping_pantry_reconcile_key_length"),
        CheckConstraint("length(request_hash) = 64", name="ck_shopping_pantry_reconcile_request_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
