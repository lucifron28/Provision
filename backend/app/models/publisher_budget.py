from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class PublisherBudget(Base):
    __tablename__ = "publisher_budget"
    __table_args__ = (CheckConstraint("id = 1", name="ck_publisher_budget_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    used: Mapped[int] = mapped_column(Integer, nullable=False)
    window_started: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PublisherPacing(Base):
    __tablename__ = "publisher_pacing"
    source_id: Mapped[int] = mapped_column(ForeignKey("recipe_sources.id", ondelete="RESTRICT"), primary_key=True)
    window_started: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_used: Mapped[int] = mapped_column(Integer, nullable=False)
    next_allowed: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paused: Mapped[bool] = mapped_column(Boolean, nullable=False)
