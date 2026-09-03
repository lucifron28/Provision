from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field
from app.models.session import GrocerySessionStatus
from app.schemas.batch import InventoryBatchRead


class GrocerySessionBase(BaseModel):
    store_name: str = Field(..., min_length=1, max_length=255, description="Supermarket / store name")
    purchase_date: Optional[datetime] = Field(None, description="Date and time of purchase")
    total_amount: Optional[float] = Field(None, ge=0, description="Receipt or basket total amount")
    notes: Optional[str] = Field(None, description="Optional notes, receipt OCR metadata, etc.")


class GrocerySessionCreate(GrocerySessionBase):
    pass


class GrocerySessionUpdate(BaseModel):
    store_name: Optional[str] = Field(None, min_length=1, max_length=255)
    purchase_date: Optional[datetime] = None
    total_amount: Optional[float] = Field(None, ge=0)
    status: Optional[GrocerySessionStatus] = None
    notes: Optional[str] = None


class SessionItemInput(BaseModel):
    product_id: int = Field(..., description="Referenced Product ID")
    storage_location_id: Optional[int] = Field(None, description="Storage location ID")
    quantity: float = Field(..., gt=0, description="Quantity purchased")
    unit_price: Optional[float] = Field(None, ge=0, description="Unit price from receipt or scan")
    expiration_date: Optional[date] = Field(None, description="Detected or manual expiration date")


class CommitSessionRequest(BaseModel):
    items: Optional[List[SessionItemInput]] = Field(None, description="Optional list of items to ingest on commit")
    total_amount: Optional[float] = Field(None, ge=0, description="Final receipt total")
    notes: Optional[str] = None


class GrocerySessionRead(GrocerySessionBase):
    id: int
    status: GrocerySessionStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GrocerySessionWithBatches(GrocerySessionRead):
    batches: List[InventoryBatchRead] = []
