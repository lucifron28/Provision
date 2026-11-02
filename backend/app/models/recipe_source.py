from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class RecipeSource(Base, TimestampMixin):
    __tablename__ = "recipe_sources"
    __table_args__ = (CheckConstraint("revision > 0", name="ck_recipe_source_revision"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_host: Mapped[str] = mapped_column(String(253), nullable=False, unique=True)
    publisher_name: Mapped[str] = mapped_column(String(200), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    policy: Mapped[dict] = mapped_column(JSONB, nullable=False)


class RecipeSourceReview(Base):
    __tablename__ = "recipe_source_reviews"
    __table_args__ = (UniqueConstraint("source_id", "revision", name="uq_recipe_source_review_revision"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("recipe_sources.id", ondelete="RESTRICT"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    reviewed_by: Mapped[str] = mapped_column(String(200), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)


class RecipeSourceReference(Base, TimestampMixin):
    __tablename__ = "recipe_source_references"
    __table_args__ = (
        ForeignKeyConstraint(["household_id", "recipe_id"], ["recipes.household_id", "recipes.id"],
            name="fk_recipe_source_reference_household", ondelete="CASCADE"),
        UniqueConstraint("household_id", "recipe_id", name="uq_recipe_source_reference_recipe"),
        CheckConstraint("revision > 0", name="ck_recipe_source_reference_revision"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(Integer, nullable=False)
    recipe_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("recipe_sources.id", ondelete="RESTRICT"), nullable=True)
    canonical_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    author: Mapped[str | None] = mapped_column(String(200), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    broader_web_permission: Mapped[bool] = mapped_column(Boolean, nullable=False)
    linked_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
