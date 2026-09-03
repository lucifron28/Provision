from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.product import ProductRead
from app.schemas.location import StorageLocationRead


class InventoryBatchBase(BaseModel):
    product_id: int = Field(..., description="ID of the referenced product")
    storage_location_id: Optional[int] = Field(None, description="Storage location ID, e.g. Pantry")
    grocery_session_id: Optional[int] = Field(None, description="Linked grocery intake session ID")
    purchased_at: Optional[datetime] = Field(None, description="Purchase date and time")
    expiration_date: Optional[date] = Field(None, description="Expiration date (YYYY-MM-DD)")
    original_quantity: float = Field(..., gt=0, description="Original purchase quantity")
    unit_price: Optional[Decimal] = Field(None, ge=Decimal("0.00"), description="Cost per unit at purchase")


class InventoryBatchCreate(InventoryBatchBase):
    pass


class InventoryBatchUpdate(BaseModel):
    storage_location_id: Optional[int] = None
    expiration_date: Optional[date] = None
    unit_price: Optional[Decimal] = Field(None, ge=Decimal("0.00"))


class InventoryBatchRead(InventoryBatchBase):
    id: int
    remaining_quantity: float
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InventoryBatchWithDetails(InventoryBatchRead):
    product: Optional[ProductRead] = None
    storage_location: Optional[StorageLocationRead] = None
