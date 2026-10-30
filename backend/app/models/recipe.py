from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, ForeignKeyConstraint, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Recipe(Base, TimestampMixin):
    __tablename__ = "recipes"
    __table_args__ = (
        UniqueConstraint("household_id", "id", name="uq_recipes_household_id"),
        CheckConstraint("revision > 0", name="ck_recipes_revision"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id", ondelete="RESTRICT"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    cuisine: Mapped[str] = mapped_column(String(80), nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"
    __table_args__ = (
        ForeignKeyConstraint(["household_id", "recipe_id"], ["recipes.household_id", "recipes.id"],
            name="fk_recipe_ingredient_household", ondelete="CASCADE"),
        UniqueConstraint("household_id", "recipe_id", "position", name="uq_recipe_ingredient_position"),
        CheckConstraint("amount > 0", name="ck_recipe_ingredient_amount"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(Integer, nullable=False)
    recipe_id: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    ingredient_id: Mapped[int | None] = mapped_column(ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=True)
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    preparation: Mapped[str | None] = mapped_column(String(500), nullable=True)
    substitution_options: Mapped[list] = mapped_column(JSONB, nullable=False)


class RecipeRevision(Base):
    __tablename__ = "recipe_revisions"
    __table_args__ = (
        ForeignKeyConstraint(["household_id", "recipe_id"], ["recipes.household_id", "recipes.id"],
            name="fk_recipe_revision_household", ondelete="CASCADE"),
        UniqueConstraint("household_id", "recipe_id", "revision", name="uq_recipe_revision"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(Integer, nullable=False)
    recipe_id: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)


class SavedRecipe(Base, TimestampMixin):
    __tablename__ = "saved_recipes"
    __table_args__ = (
        ForeignKeyConstraint(["household_id", "member_user_id"],
            ["household_memberships.household_id", "household_memberships.user_id"],
            name="fk_saved_recipe_membership", ondelete="CASCADE"),
        ForeignKeyConstraint(["household_id", "recipe_id", "recipe_revision"],
            ["recipe_revisions.household_id", "recipe_revisions.recipe_id", "recipe_revisions.revision"],
            name="fk_saved_recipe_revision", ondelete="CASCADE"),
        UniqueConstraint("household_id", "member_user_id", "recipe_id", name="uq_saved_recipe_member"),
        CheckConstraint("revision > 0", name="ck_saved_recipe_revision"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(Integer, nullable=False)
    member_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    recipe_id: Mapped[int] = mapped_column(Integer, nullable=False)
    recipe_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_saved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    servings: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
