from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field
from app.models.event import EventType


class InventoryEventRead(BaseModel):
    id: int
    batch_id: int
    event_type: EventType
    quantity: float
    occurred_at: datetime
    reason: Optional[str] = None
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ConsumeRequest(BaseModel):
    product_id: int = Field(..., description="Product ID to consume from")
    quantity: float = Field(..., gt=0, description="Amount to consume")
    reason: Optional[str] = Field("Household consumption", description="Reason for consuming")
    notes: Optional[str] = Field(None, description="Optional details or recipe notes")


class BatchDeduction(BaseModel):
    batch_id: int
    quantity_deducted: float
    remaining_in_batch: float
    expiration_date: Optional[date] = None


class ConsumeResponse(BaseModel):
    product_id: int
    requested_quantity: float
    total_consumed: float
    batches_deducted: List[BatchDeduction]
    new_total_stock: float


class DiscardRequest(BaseModel):
    reason: Optional[str] = Field("Spoiled / Expired", description="Reason for discarding batch")
    notes: Optional[str] = Field(None, description="Additional context")


class AdjustmentRequest(BaseModel):
    new_remaining_quantity: float = Field(..., ge=0, description="Actual physical count")
    reason: str = Field(..., min_length=1, description="Reason for discrepancy")
    notes: Optional[str] = Field(None, description="Additional notes")
