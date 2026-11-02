from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Ingredient(Base, TimestampMixin):
    """Curated global ingredient name, independent of household products."""

    __tablename__ = "ingredients"
    __table_args__ = (
        UniqueConstraint("normalized_name", name="uq_ingredients_normalized_name"),
        CheckConstraint(
            "default_dimension IS NULL OR default_dimension IN ('mass', 'volume', 'count')",
            name="ck_ingredients_default_dimension",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    canonical_name: Mapped[str] = mapped_column(String(160), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(180), nullable=False)
    filipino_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    family: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    default_dimension: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    default_unit: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )


class IngredientAlias(Base, TimestampMixin):
    """Reviewed Filipino or English search term for a global ingredient."""

    __tablename__ = "ingredient_aliases"
    __table_args__ = (
        UniqueConstraint(
            "ingredient_id", "normalized_alias", "language",
            name="uq_ingredient_alias_scope",
        ),
        Index("ix_ingredient_aliases_normalized_alias", "normalized_alias"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(String(180), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(180), nullable=False)
    language: Mapped[str] = mapped_column(String(12), nullable=False)
    region: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProductIngredientMapping(Base, TimestampMixin):
    """Versioned, household-owned mapping from a product to a food ingredient."""

    __tablename__ = "product_ingredient_mappings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["household_id", "product_id"],
            ["products.household_id", "products.id"],
            name="fk_product_ingredient_mappings_household_product",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "household_id", "product_id", "version",
            name="uq_product_ingredient_mapping_version",
        ),
        UniqueConstraint("household_id", "id", name="uq_product_ingredient_mapping_household_id"),
        Index(
            "uq_product_ingredient_mapping_current",
            "household_id", "product_id", unique=True,
            postgresql_where=text("is_current IS TRUE"),
            sqlite_where=text("is_current = 1"),
        ),
        CheckConstraint("version > 0", name="ck_product_ingredient_mapping_version"),
        CheckConstraint(
            "mode IN ('DIRECT', 'COMPOSITE', 'UNKNOWN')",
            name="ck_product_ingredient_mapping_mode",
        ),
        CheckConstraint(
            "verification_status IN ('UNVERIFIED', 'VERIFIED', 'UNKNOWN')",
            name="ck_product_ingredient_mapping_verification",
        ),
        CheckConstraint(
            "(mode = 'DIRECT' AND ingredient_id IS NOT NULL) OR "
            "(mode IN ('COMPOSITE', 'UNKNOWN') AND ingredient_id IS NULL)",
            name="ck_product_ingredient_mapping_target",
        ),
        CheckConstraint(
            "mode != 'UNKNOWN' OR (verification_status = 'UNKNOWN' AND unknown_composition IS TRUE)",
            name="ck_product_ingredient_mapping_unknown_state",
        ),
        CheckConstraint(
            "verification_status != 'VERIFIED' OR verified_at IS NOT NULL",
            name="ck_product_ingredient_mapping_verified_at",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_product_ingredient_mapping_confidence",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    ingredient_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    verification_status: Mapped[str] = mapped_column(String(16), nullable=False)
    method: Mapped[str] = mapped_column(String(80), nullable=False)
    verified_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4), nullable=True)
    unknown_composition: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )


class ProductIngredientMappingTarget(Base, TimestampMixin):
    """Ingredient identity attached to a mapping, for direct or composite products."""

    __tablename__ = "product_ingredient_mapping_targets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["household_id", "product_id", "mapping_version"],
            [
                "product_ingredient_mappings.household_id",
                "product_ingredient_mappings.product_id",
                "product_ingredient_mappings.version",
            ],
            name="fk_product_ingredient_target_mapping",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "household_id", "product_id", "mapping_version", "ingredient_id",
            name="uq_product_ingredient_mapping_target_scope",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    household_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(Integer, nullable=False)
    mapping_version: Mapped[int] = mapped_column(Integer, nullable=False)
    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False, index=True
    )


class ProductPackageFactor(Base, TimestampMixin):
    """Verified conversion from one inventory product unit to an ingredient amount."""

    __tablename__ = "product_package_factors"
    __table_args__ = (
        ForeignKeyConstraint(
            ["household_id", "product_id", "mapping_version"],
            [
                "product_ingredient_mappings.household_id",
                "product_ingredient_mappings.product_id",
                "product_ingredient_mappings.version",
            ],
            name="fk_product_package_factor_mapping",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["household_id", "product_id", "mapping_version", "ingredient_id"],
            [
                "product_ingredient_mapping_targets.household_id",
                "product_ingredient_mapping_targets.product_id",
                "product_ingredient_mapping_targets.mapping_version",
                "product_ingredient_mapping_targets.ingredient_id",
            ],
            name="fk_product_package_factor_mapping_target",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "household_id", "product_id", "mapping_version", "ingredient_id",
            name="uq_product_package_factor_scope",
        ),
        CheckConstraint("ingredient_amount > 0", name="ck_product_package_factor_amount"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    household_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(Integer, nullable=False)
    mapping_version: Mapped[int] = mapped_column(Integer, nullable=False)
    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    inventory_unit: Mapped[str] = mapped_column(String(50), nullable=False)
    ingredient_amount: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    ingredient_unit: Mapped[str] = mapped_column(String(24), nullable=False)
    source_reference: Mapped[str] = mapped_column(Text, nullable=False)
    verified_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
