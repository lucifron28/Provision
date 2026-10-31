from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class IngredientAllergen(Base):
    """Curated conceptual association, never a packaged-product clearance."""
    __tablename__ = "ingredient_allergens"
    __table_args__ = (
        UniqueConstraint("ingredient_id", "allergen_code", name="uq_ingredient_allergen"),
        CheckConstraint("relation IN ('DIRECT', 'DERIVATIVE', 'POSSIBLE', 'UNKNOWN')", name="ck_ingredient_allergen_relation"),
        CheckConstraint("length(trim(evidence_reference)) > 0", name="ck_ingredient_allergen_evidence"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id", ondelete="CASCADE"), index=True)
    allergen_code: Mapped[str] = mapped_column(String(32), nullable=False)
    relation: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_reference: Mapped[str] = mapped_column(Text, nullable=False)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IngredientDerivative(Base):
    __tablename__ = "ingredient_derivatives"
    __table_args__ = (
        UniqueConstraint("ingredient_id", "parent_ingredient_id", name="uq_ingredient_derivative"),
        CheckConstraint("ingredient_id <> parent_ingredient_id", name="ck_ingredient_derivative_not_self"),
        CheckConstraint("length(trim(evidence_reference)) > 0", name="ck_ingredient_derivative_evidence"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id", ondelete="CASCADE"), index=True)
    parent_ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False)
    evidence_reference: Mapped[str] = mapped_column(Text, nullable=False)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
