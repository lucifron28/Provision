from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MealDBBudget(Base):
    __tablename__ = "themealdb_budget"
    __table_args__ = (CheckConstraint("id = 1", name="ck_themealdb_budget_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    used: Mapped[int] = mapped_column(Integer, nullable=False)
    next_allowed: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paused: Mapped[bool] = mapped_column(Boolean, nullable=False)
