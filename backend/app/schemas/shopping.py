from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.product import ProductRead


class ShoppingListItemBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Item name")
    product_id: Optional[int] = Field(None, description="Optional linked product ID")
    quantity: float = Field(1.0, gt=0, description="Quantity to purchase")
    unit: Optional[str] = Field(None, max_length=50, description="Unit of measurement")
    notes: Optional[str] = Field(None, description="Notes, e.g. preferred brand")


class ShoppingListItemCreate(BaseModel):
    name: Optional[str] = Field(None, max_length=255, description="Item name (optional if product_id provided)")
    product_id: Optional[int] = Field(None, description="Optional linked product ID")
    quantity: float = Field(1.0, gt=0, description="Quantity to purchase")
    unit: Optional[str] = Field(None, max_length=50, description="Unit of measurement")
    notes: Optional[str] = None


class ShoppingListItemUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    product_id: Optional[int] = None
    quantity: Optional[float] = Field(None, gt=0)
    unit: Optional[str] = Field(None, max_length=50)
    is_bought: Optional[bool] = None
    notes: Optional[str] = None


class ShoppingListItemRead(ShoppingListItemBase):
    id: int
    is_bought: bool
    created_at: datetime
    updated_at: datetime
    product: Optional[ProductRead] = None

    model_config = ConfigDict(from_attributes=True)


class AutoGenerateShoppingRequest(BaseModel):
    threshold: float = Field(1.0, ge=0, description="Trigger threshold: add products with total stock <= threshold")
