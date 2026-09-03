from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Numeric, Boolean, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.product import Product


class ShoppingListItem(Base, TimestampMixin):
    __tablename__ = "shopping_list_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)

    # In case the user writes an item before linking a product
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), default=1.0, nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_bought: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    product: Mapped[Optional["Product"]] = relationship("Product")
