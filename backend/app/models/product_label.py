from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, CheckConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProductAllergenLabel(Base):
    __tablename__ = "product_allergen_labels"
    __table_args__ = (
        ForeignKeyConstraint(["household_id", "product_id", "mapping_version"],
            ["product_ingredient_mappings.household_id", "product_ingredient_mappings.product_id", "product_ingredient_mappings.version"],
            name="fk_product_allergen_label_mapping", ondelete="CASCADE"),
        UniqueConstraint("household_id", "product_id", "revision", name="uq_product_allergen_label_revision"),
        Index("uq_product_allergen_label_current", "household_id", "product_id", unique=True,
            postgresql_where=text("is_current IS TRUE")),
        CheckConstraint("revision > 0", name="ck_product_allergen_label_revision"),
        CheckConstraint("length(trim(source_reference)) > 0", name="ck_product_allergen_label_source"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[int] = mapped_column(Integer, nullable=False)
    mapping_version: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    product_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    declared_allergens: Mapped[list] = mapped_column(JSONB, nullable=False)
    possible_allergens: Mapped[list] = mapped_column(JSONB, nullable=False)
    custom_allergens: Mapped[list] = mapped_column(JSONB, nullable=False)
    composition_known: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_reference: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
