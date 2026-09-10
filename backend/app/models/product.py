import enum
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Enum as SQLEnum, Float
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

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    brand: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    barcode: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True, nullable=True)
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
        back_populates="product",
    )
