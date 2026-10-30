from decimal import Decimal
from typing import Optional, TYPE_CHECKING
from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Integer, String, Numeric, Boolean, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.product import Product


class ShoppingListItem(Base, TimestampMixin):
    __tablename__ = "shopping_list_items"
    __table_args__ = (
        UniqueConstraint("household_id", "id", name="uq_shopping_items_household_id"),
        ForeignKeyConstraint(
            ["household_id", "product_id"],
            ["products.household_id", "products.id"],
            name="fk_shopping_items_household_product",
            ondelete="SET NULL (product_id)",
        ),
        ForeignKeyConstraint(
            ["household_id", "origin_recipe_id", "origin_recipe_revision"],
            ["recipe_revisions.household_id", "recipe_revisions.recipe_id", "recipe_revisions.revision"],
            name="fk_shopping_items_household_recipe_revision",
            ondelete="SET NULL (origin_recipe_id, origin_recipe_revision)",
        ),
        ForeignKeyConstraint(
            ["household_id", "origin_plan_id", "origin_plan_revision"],
            ["meal_plan_revisions.household_id", "meal_plan_revisions.plan_id", "meal_plan_revisions.revision"],
            name="fk_shopping_items_household_plan_revision",
            ondelete="SET NULL (origin_plan_id, origin_plan_revision)",
        ),
        CheckConstraint(
            "(origin_recipe_id IS NULL AND origin_recipe_revision IS NULL) OR "
            "(origin_recipe_id IS NOT NULL AND origin_recipe_revision IS NOT NULL)",
            name="ck_shopping_items_origin_recipe_pair",
        ),
        CheckConstraint(
            "(origin_plan_id IS NULL AND origin_plan_revision IS NULL) OR "
            "(origin_plan_id IS NOT NULL AND origin_plan_revision IS NOT NULL)",
            name="ck_shopping_items_origin_plan_pair",
        ),
        CheckConstraint(
            "origin_recipe_id IS NULL OR origin_plan_id IS NULL",
            name="ck_shopping_items_single_origin",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    ingredient_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    origin_recipe_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    origin_recipe_revision: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    origin_plan_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    origin_plan_revision: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # In case the user writes an item before linking a product
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=Decimal("1"), nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_bought: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    product: Mapped[Optional["Product"]] = relationship(
        "Product",
        primaryjoin="and_(ShoppingListItem.household_id == Product.household_id, ShoppingListItem.product_id == Product.id)",
        foreign_keys="ShoppingListItem.product_id",
    )
