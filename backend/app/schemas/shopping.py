from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.schemas.product import ProductRead
from app.schemas.ingredients import MAX_AMOUNT


class ShoppingListItemBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Item name")
    product_id: Optional[int] = Field(None, description="Optional linked product ID")
    quantity: float = Field(1.0, gt=0, description="Quantity to purchase")
    unit: Optional[str] = Field(None, max_length=50, description="Unit of measurement")
    ingredient_id: Optional[int] = Field(None, gt=0, description="Explicit canonical ingredient identity")
    origin_recipe_id: Optional[int] = Field(None, gt=0, description="Household recipe that created this row")
    origin_recipe_revision: Optional[int] = Field(None, ge=1)
    notes: Optional[str] = Field(None, description="Notes, e.g. preferred brand")


class ShoppingListItemCreate(BaseModel):
    name: Optional[str] = Field(None, max_length=255, description="Item name (optional if product_id provided)")
    product_id: Optional[int] = Field(None, description="Optional linked product ID")
    quantity: Decimal = Field(
        default=Decimal("1"), gt=0, le=MAX_AMOUNT, max_digits=14, decimal_places=6,
        description="Quantity to purchase",
    )
    unit: Optional[str] = Field(None, max_length=50, description="Unit of measurement")
    ingredient_id: Optional[int] = Field(None, gt=0)
    origin_recipe_id: Optional[int] = Field(None, gt=0)
    notes: Optional[str] = None

    @field_validator("quantity")
    @classmethod
    def finite_quantity(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Quantity must be finite")
        return value


class ShoppingListItemUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    product_id: Optional[int] = None
    quantity: Optional[Decimal] = Field(
        default=None, gt=0, le=MAX_AMOUNT, max_digits=14, decimal_places=6
    )
    unit: Optional[str] = Field(None, max_length=50)
    ingredient_id: Optional[int] = Field(None, gt=0)
    origin_recipe_id: Optional[int] = Field(None, gt=0)
    is_bought: Optional[bool] = None
    notes: Optional[str] = None

    @field_validator("quantity")
    @classmethod
    def finite_quantity(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("Quantity must be finite")
        return value

    @model_validator(mode="after")
    def reject_null_for_required_fields(self):
        for field in ("name", "quantity", "is_bought"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ShoppingListItemRead(ShoppingListItemBase):
    id: int
    is_bought: bool
    created_at: datetime
    updated_at: datetime
    product: Optional[ProductRead] = None

    model_config = ConfigDict(from_attributes=True)


class AutoGenerateShoppingRequest(BaseModel):
    threshold: float = Field(1.0, ge=0, description="Trigger threshold: add products with total stock <= threshold")
