from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, Date, DateTime, Numeric, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.location import StorageLocation
    from app.models.session import GrocerySession
    from app.models.event import InventoryEvent


class InventoryBatch(Base, TimestampMixin):
    __tablename__ = "inventory_batches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_location_id: Mapped[Optional[int]] = mapped_column(ForeignKey("storage_locations.id", ondelete="SET NULL"), nullable=True, index=True)
    grocery_session_id: Mapped[Optional[int]] = mapped_column(ForeignKey("grocery_sessions.id", ondelete="SET NULL"), nullable=True, index=True)

    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), nullable=False)
    expiration_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)

    # Food quantities can be measured in count (e.g. 6 cans) or weights (e.g. 1.5 kg)
    original_quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    remaining_quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, index=True)

    # Unit price at time of purchase, e.g. 42.50
    unit_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="batches")
    storage_location: Mapped[Optional["StorageLocation"]] = relationship("StorageLocation", back_populates="batches")
    grocery_session: Mapped[Optional["GrocerySession"]] = relationship("GrocerySession", back_populates="batches")
    events: Mapped[List["InventoryEvent"]] = relationship("InventoryEvent", back_populates="batch", cascade="all, delete-orphan")
