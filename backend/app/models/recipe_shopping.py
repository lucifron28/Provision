from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class RecipeShoppingIdempotency(Base, TimestampMixin):
    """Persisted result for an explicitly confirmed recipe-shopping request."""

    __tablename__ = "recipe_shopping_idempotency"
    __table_args__ = (
        UniqueConstraint(
            "household_id", "idempotency_key", name="uq_recipe_shopping_household_key"
        ),
        CheckConstraint(
            "length(idempotency_key) BETWEEN 8 AND 128",
            name="ck_recipe_shopping_key_length",
        ),
        CheckConstraint("length(request_hash) = 64", name="ck_recipe_shopping_request_hash"),
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
