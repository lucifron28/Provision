import enum
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import ForeignKey, String, Enum as SQLEnum, Float, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.batch import InventoryBatch


class ProductSource(str, enum.Enum):
    USER_CONFIRMED = "USER_CONFIRMED"
    OCR_ASSISTED = "OCR_ASSISTED"
    EXTERNAL_DATABASE = "EXTERNAL_DATABASE"
    ADMIN_CREATED = "ADMIN_CREATED"


class Product(Base, TimestampMixin):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("household_id", "id", name="uq_products_household_id"),
        UniqueConstraint("household_id", "barcode", name="uq_products_household_barcode"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    brand: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    barcode: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), index=True, nullable=True)
    package_size: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source: Mapped[ProductSource] = mapped_column(
        SQLEnum(ProductSource, name="product_source_enum"),
        default=ProductSource.USER_CONFIRMED,
        nullable=False,
    )

    batches: Mapped[List["InventoryBatch"]] = relationship(
        "InventoryBatch",
        primaryjoin="and_(Product.household_id == InventoryBatch.household_id, Product.id == InventoryBatch.product_id)",
        foreign_keys="InventoryBatch.product_id",
        back_populates="product",
    )
