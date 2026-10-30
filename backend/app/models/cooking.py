from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    BigInteger,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CookingSession(Base, TimestampMixin):
    """A deliberately recorded cooking action pinned to a recipe revision."""

    __tablename__ = "cooking_sessions"
    __table_args__ = (
        UniqueConstraint("household_id", "id", name="uq_cooking_sessions_household_id"),
        ForeignKeyConstraint(
            ["household_id", "recipe_id", "recipe_revision"],
            ["recipe_revisions.household_id", "recipe_revisions.recipe_id", "recipe_revisions.revision"],
            name="fk_cooking_session_recipe_revision",
            ondelete="RESTRICT",
        ),
        CheckConstraint("recipe_revision > 0", name="ck_cooking_session_recipe_revision"),
        CheckConstraint("servings > 0", name="ck_cooking_session_servings"),
        CheckConstraint("source_reference_revision IS NULL OR source_reference_revision > 0",
                        name="ck_cooking_session_source_reference_revision"),
        CheckConstraint("source_revision IS NULL OR source_revision > 0",
                        name="ck_cooking_session_source_revision"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    recipe_id: Mapped[int] = mapped_column(Integer, nullable=False)
    recipe_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    servings: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    inventory_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_reference_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipe_source_references.id", ondelete="SET NULL"), nullable=True
    )
    source_reference_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipe_sources.id", ondelete="SET NULL"), nullable=True
    )
    source_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CookingConsumption(Base):
    """Canonical ingredient usage linked to the inventory event that deducted it."""

    __tablename__ = "cooking_consumptions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["household_id", "cooking_session_id"],
            ["cooking_sessions.household_id", "cooking_sessions.id"],
            name="fk_cooking_consumption_session",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["household_id", "batch_id"],
            ["inventory_batches.household_id", "inventory_batches.id"],
            name="fk_cooking_consumption_batch",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "household_id", "cooking_session_id", "batch_id",
            name="uq_cooking_consumption_session_batch",
        ),
        UniqueConstraint("inventory_event_id", name="uq_cooking_consumption_inventory_event"),
        CheckConstraint("ingredient_quantity > 0", name="ck_cooking_consumption_quantity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    cooking_session_id: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    inventory_event_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_events.id", ondelete="RESTRICT"), nullable=False
    )
    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ingredient_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    ingredient_unit: Mapped[str] = mapped_column(String(24), nullable=False)


class CookingIdempotency(Base, TimestampMixin):
    __tablename__ = "cooking_idempotency"
    __table_args__ = (
        UniqueConstraint(
            "household_id", "idempotency_key", name="uq_cooking_idempotency_household_key"
        ),
        ForeignKeyConstraint(
            ["household_id", "cooking_session_id"],
            ["cooking_sessions.household_id", "cooking_sessions.id"],
            name="fk_cooking_idempotency_session",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "length(idempotency_key) BETWEEN 8 AND 128",
            name="ck_cooking_idempotency_key_length",
        ),
        CheckConstraint("length(request_hash) = 64", name="ck_cooking_idempotency_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cooking_session_id: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
