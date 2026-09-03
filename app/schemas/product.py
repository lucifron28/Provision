from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.product import ProductSource


class ProductBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Product display name")
    brand: Optional[str] = Field(None, max_length=255, description="Manufacturer/brand name")
    barcode: Optional[str] = Field(None, max_length=100, description="UPC/EAN barcode string")
    category: Optional[str] = Field(None, max_length=100, description="Product category, e.g. Dairy, Canned")
    package_size: Optional[float] = Field(None, gt=0, description="Package size amount")
    unit: Optional[str] = Field(None, max_length=50, description="Measurement unit (g, ml, cans, pcs)")
    image_url: Optional[str] = Field(None, max_length=500, description="Product image URL")
    source: ProductSource = Field(default=ProductSource.USER_CONFIRMED, description="Product metadata source")


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    brand: Optional[str] = Field(None, max_length=255)
    barcode: Optional[str] = Field(None, max_length=100)
    category: Optional[str] = Field(None, max_length=100)
    package_size: Optional[float] = Field(None, gt=0)
    unit: Optional[str] = Field(None, max_length=50)
    image_url: Optional[str] = Field(None, max_length=500)
    source: Optional[ProductSource] = None


class ProductRead(ProductBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductWithStock(ProductRead):
    total_remaining_quantity: float = 0.0
    active_batches_count: int = 0
