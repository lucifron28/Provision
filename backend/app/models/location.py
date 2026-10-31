from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.batch import InventoryBatch


class StorageLocation(Base, TimestampMixin):
    __tablename__ = "storage_locations"
    __table_args__ = (
        UniqueConstraint("household_id", "id", name="uq_storage_locations_household_id"),
        UniqueConstraint("household_id", "name", name="uq_storage_locations_household_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    batches: Mapped[List["InventoryBatch"]] = relationship(
        "InventoryBatch",
        primaryjoin="and_(StorageLocation.household_id == InventoryBatch.household_id, StorageLocation.id == InventoryBatch.storage_location_id)",
        foreign_keys="InventoryBatch.storage_location_id",
        back_populates="storage_location",
    )
