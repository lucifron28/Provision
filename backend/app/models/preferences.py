from typing import Optional

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class FoodPreference(Base, TimestampMixin):
    """A member's private profile, or an owner-managed household profile."""

    __tablename__ = "food_preferences"
    __table_args__ = (
        ForeignKeyConstraint(["household_id", "member_user_id"],
            ["household_memberships.household_id", "household_memberships.user_id"],
            ondelete="CASCADE", name="fk_food_preferences_membership"),
        Index("uq_food_preferences_member", "household_id", "member_user_id", unique=True,
            postgresql_where=text("member_user_id IS NOT NULL")),
        Index("uq_food_preferences_household", "household_id", unique=True,
            postgresql_where=text("member_user_id IS NULL")),
        CheckConstraint("revision > 0", name="ck_food_preferences_revision"),
        CheckConstraint("allergy_status IN ('NOT_PROVIDED', 'NONE_DECLARED', 'DECLARED')",
            name="ck_food_preferences_allergy_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    member_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    preferences: Mapped[dict] = mapped_column(JSONB, nullable=False)
    allergy_status: Mapped[str] = mapped_column(String(16), nullable=False)


class FoodAllergy(Base):
    """Explicit declarations kept separate from dislikes and diet preferences."""

    __tablename__ = "food_allergies"
    __table_args__ = (
        CheckConstraint("(allergen_code IS NOT NULL) <> (custom_text IS NOT NULL)",
            name="ck_food_allergies_reference"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("food_preferences.id", ondelete="CASCADE"), index=True)
    allergen_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    custom_text: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)
    severity: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    cross_contact_concern: Mapped[bool] = mapped_column(nullable=False, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
