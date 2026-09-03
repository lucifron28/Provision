import enum
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Enum as SQLEnum, DateTime, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.batch import InventoryBatch


class GrocerySessionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class GrocerySession(Base, TimestampMixin):
    __tablename__ = "grocery_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_name: Mapped[str] = mapped_column(String(255), nullable=False)
    purchase_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), nullable=False)
    total_amount: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    status: Mapped[GrocerySessionStatus] = mapped_column(
        SQLEnum(GrocerySessionStatus, name="grocery_session_status_enum"),
        default=GrocerySessionStatus.DRAFT,
        nullable=False,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    batches: Mapped[List["InventoryBatch"]] = relationship("InventoryBatch", back_populates="grocery_session")
