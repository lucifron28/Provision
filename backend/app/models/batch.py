from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.location import StorageLocation
    from app.models.session import GrocerySession
    from app.models.event import InventoryEvent


class InventoryBatch(Base, TimestampMixin):
    __tablename__ = "inventory_batches"
    __table_args__ = (
        UniqueConstraint("household_id", "id", name="uq_inventory_batches_household_id"),
        ForeignKeyConstraint(
            ["household_id", "product_id"],
            ["products.household_id", "products.id"],
            name="fk_inventory_batches_household_product",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["household_id", "storage_location_id"],
            ["storage_locations.household_id", "storage_locations.id"],
            name="fk_inventory_batches_household_location",
            ondelete="SET NULL (storage_location_id)",
        ),
        ForeignKeyConstraint(
            ["household_id", "grocery_session_id"],
            ["grocery_sessions.household_id", "grocery_sessions.id"],
            name="fk_inventory_batches_household_session",
            ondelete="SET NULL (grocery_session_id)",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    storage_location_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    grocery_session_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), nullable=False)
    expiration_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)

    # Food quantities can be measured in count (e.g. 6 cans) or weights (e.g. 1.5 kg)
    original_quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    remaining_quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, index=True)

    # Unit price at time of purchase, e.g. 42.50
    unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)

    # Relationships
    product: Mapped["Product"] = relationship(
        "Product",
        primaryjoin="and_(InventoryBatch.household_id == Product.household_id, InventoryBatch.product_id == Product.id)",
        foreign_keys="InventoryBatch.product_id",
        back_populates="batches",
    )
    storage_location: Mapped[Optional["StorageLocation"]] = relationship(
        "StorageLocation",
        primaryjoin="and_(InventoryBatch.household_id == StorageLocation.household_id, InventoryBatch.storage_location_id == StorageLocation.id)",
        foreign_keys="InventoryBatch.storage_location_id",
        back_populates="batches",
    )
    grocery_session: Mapped[Optional["GrocerySession"]] = relationship(
        "GrocerySession",
        primaryjoin="and_(InventoryBatch.household_id == GrocerySession.household_id, InventoryBatch.grocery_session_id == GrocerySession.id)",
        foreign_keys="InventoryBatch.grocery_session_id",
        back_populates="batches",
    )
    events: Mapped[List["InventoryEvent"]] = relationship("InventoryEvent", back_populates="batch")
