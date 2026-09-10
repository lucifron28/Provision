import enum
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Enum as SQLEnum, DateTime, Numeric, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.batch import InventoryBatch


class EventType(str, enum.Enum):
    PURCHASED = "PURCHASED"
    CONSUMED = "CONSUMED"
    DISCARDED = "DISCARDED"
    EXPIRED = "EXPIRED"
    ADJUSTMENT = "ADJUSTMENT"
    TRANSFERRED = "TRANSFERRED"


class InventoryEvent(Base):
    __tablename__ = "inventory_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("inventory_batches.id", ondelete="RESTRICT"), nullable=False, index=True)
    event_type: Mapped[EventType] = mapped_column(SQLEnum(EventType, name="event_type_enum"), nullable=False, index=True)

    # Quantity changed (signed delta for ADJUSTMENT, positive amount for others)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), nullable=False, index=True)

    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    batch: Mapped["InventoryBatch"] = relationship("InventoryBatch", back_populates="events")
