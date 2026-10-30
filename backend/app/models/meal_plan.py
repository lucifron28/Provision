"""Household-scoped weekly meal plans and immutable revisions."""

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class MealPlan(Base, TimestampMixin):
    __tablename__ = "meal_plans"
    __table_args__ = (
        UniqueConstraint("household_id", "id", name="uq_meal_plans_household_id"),
        UniqueConstraint("household_id", "week_start", name="uq_meal_plans_household_week"),
        CheckConstraint("revision > 0", name="ck_meal_plans_revision"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class MealPlanEntry(Base):
    __tablename__ = "meal_plan_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["household_id", "plan_id"],
            ["meal_plans.household_id", "meal_plans.id"],
            name="fk_meal_plan_entry_household_plan",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["household_id", "recipe_id", "recipe_revision"],
            ["recipe_revisions.household_id", "recipe_revisions.recipe_id", "recipe_revisions.revision"],
            name="fk_meal_plan_entry_recipe_revision",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("household_id", "id", name="uq_meal_plan_entries_household_id"),
        UniqueConstraint(
            "household_id", "plan_id", "meal_date", "slot", "position",
            name="uq_meal_plan_entry_slot_position",
        ),
        CheckConstraint(
            "slot IN ('breakfast', 'lunch', 'dinner', 'merienda')",
            name="ck_meal_plan_entry_slot",
        ),
        CheckConstraint("position BETWEEN 0 AND 9", name="ck_meal_plan_entry_position"),
        CheckConstraint("servings > 0", name="ck_meal_plan_entry_servings"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    household_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    plan_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    meal_date: Mapped[date] = mapped_column(Date, nullable=False)
    slot: Mapped[str] = mapped_column(String(16), nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    recipe_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    recipe_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    servings: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)


class MealPlanRevision(Base, TimestampMixin):
    __tablename__ = "meal_plan_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["household_id", "plan_id"],
            ["meal_plans.household_id", "meal_plans.id"],
            name="fk_meal_plan_revision_household_plan",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "household_id", "plan_id", "revision", name="uq_meal_plan_revision"
        ),
        CheckConstraint("revision > 0", name="ck_meal_plan_revision_revision"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    household_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    plan_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
