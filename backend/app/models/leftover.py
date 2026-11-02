import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class LeftoverEventType(str, enum.Enum):
    CONSUMED = "CONSUMED"
    DISCARDED = "DISCARDED"


class Leftover(Base, TimestampMixin):
    __tablename__ = "leftovers"
    __table_args__ = (
        UniqueConstraint("household_id", "id", name="uq_leftovers_household_id"),
        ForeignKeyConstraint(
            ["household_id", "storage_location_id"],
            ["storage_locations.household_id", "storage_locations.id"],
            name="fk_leftovers_household_location",
            ondelete="SET NULL (storage_location_id)",
        ),
        ForeignKeyConstraint(
            ["household_id", "recipe_id", "recipe_revision"],
            ["recipe_revisions.household_id", "recipe_revisions.recipe_id", "recipe_revisions.revision"],
            name="fk_leftovers_recipe_revision",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["household_id", "cooking_session_id"],
            ["cooking_sessions.household_id", "cooking_sessions.id"],
            name="fk_leftovers_cooking_session",
            ondelete="SET NULL (cooking_session_id)",
        ),
        CheckConstraint(
            "(recipe_id IS NULL AND recipe_revision IS NULL) OR "
            "(recipe_id IS NOT NULL AND recipe_revision IS NOT NULL)",
            name="ck_leftovers_recipe_revision_pair",
        ),
        CheckConstraint("quantity > 0", name="ck_leftovers_quantity_positive"),
        CheckConstraint(
            "remaining_quantity >= 0 AND remaining_quantity <= quantity",
            name="ck_leftovers_remaining_quantity",
        ),
        CheckConstraint(
            "(portions IS NULL AND remaining_portions IS NULL) OR "
            "(portions IS NOT NULL AND remaining_portions IS NOT NULL AND "
            "portions > 0 AND remaining_portions >= 0 AND remaining_portions <= portions)",
            name="ck_leftovers_remaining_portions",
        ),
        CheckConstraint(
            "(use_by_date IS NULL AND use_by_date_verified IS FALSE) OR "
            "(use_by_date IS NOT NULL AND use_by_date_verified IS TRUE)",
            name="ck_leftovers_use_by_verification",
        ),
        CheckConstraint("revision > 0", name="ck_leftovers_revision"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    recipe_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recipe_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cooking_session_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    storage_location_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    prepared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    use_by_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    use_by_date_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    remaining_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(24), nullable=False)
    portions: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    remaining_portions: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LeftoverEvent(Base):
    __tablename__ = "leftover_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["household_id", "leftover_id"],
            ["leftovers.household_id", "leftovers.id"],
            name="fk_leftover_events_household_leftover",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["household_id", "cooking_session_id"],
            ["cooking_sessions.household_id", "cooking_sessions.id"],
            name="fk_leftover_events_cooking_session",
            ondelete="SET NULL (cooking_session_id)",
        ),
        CheckConstraint("event_type IN ('CONSUMED', 'DISCARDED')", name="ck_leftover_event_type"),
        CheckConstraint("quantity > 0", name="ck_leftover_event_quantity"),
        CheckConstraint("portions IS NULL OR portions > 0", name="ck_leftover_event_portions"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    leftover_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    cooking_session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(24), nullable=False)
    portions: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
