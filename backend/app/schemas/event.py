from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.models.event import EventType


MAX_STOCK_ACTION_AMOUNT = Decimal("99999999.99")


def _clean_idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not 8 <= len(value) <= 128:
        raise ValueError("Idempotency key must contain between 8 and 128 non-blank characters")
    return value


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
    quantity: Decimal = Field(..., gt=0, le=MAX_STOCK_ACTION_AMOUNT, max_digits=10, decimal_places=2,
                              description="Amount to consume")
    reason: Optional[str] = Field("Household consumption", description="Reason for consuming")
    notes: Optional[str] = Field(None, description="Optional details or recipe notes")
    idempotency_key: Optional[str] = Field(None, min_length=8, max_length=128)

    @field_validator("quantity")
    @classmethod
    def finite_quantity(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Consumption quantity must be finite")
        return value

    @field_validator("idempotency_key")
    @classmethod
    def clean_key(cls, value: str | None) -> str | None:
        return _clean_idempotency_key(value)


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
    reason: Optional[str] = Field("Spoiled / Expired", max_length=255, description="Reason for discarding batch")
    notes: Optional[str] = Field(None, description="Additional context")
    quantity: Decimal | None = Field(None, gt=0, le=MAX_STOCK_ACTION_AMOUNT,
                                     max_digits=10, decimal_places=2,
                                     description="Amount to discard; omitted means the full batch")
    expected_updated_at: datetime | None = None
    idempotency_key: Optional[str] = Field(None, min_length=8, max_length=128)

    @field_validator("quantity")
    @classmethod
    def finite_quantity(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("Discard quantity must be finite")
        return value

    @field_validator("expected_updated_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Expected batch timestamp must include a timezone")
        return value

    @field_validator("idempotency_key")
    @classmethod
    def clean_key(cls, value: str | None) -> str | None:
        return _clean_idempotency_key(value)

    @field_validator("reason")
    @classmethod
    def require_nonblank_reason(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Discard reason must not be blank")
        return value


class AdjustmentRequest(BaseModel):
    new_remaining_quantity: Decimal = Field(..., ge=0, le=MAX_STOCK_ACTION_AMOUNT,
                                            max_digits=10, decimal_places=2,
                                            description="Actual physical count")
    reason: str = Field(..., min_length=1, max_length=180, description="Reason for discrepancy")
    notes: Optional[str] = Field(None, description="Additional notes")
    expected_updated_at: datetime | None = None
    idempotency_key: Optional[str] = Field(None, min_length=8, max_length=128)

    @field_validator("new_remaining_quantity")
    @classmethod
    def finite_quantity(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Adjusted quantity must be finite")
        return value

    @field_validator("expected_updated_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Expected batch timestamp must include a timezone")
        return value

    @field_validator("idempotency_key")
    @classmethod
    def clean_key(cls, value: str | None) -> str | None:
        return _clean_idempotency_key(value)

    @field_validator("reason")
    @classmethod
    def require_nonblank_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Adjustment reason must not be blank")
        return value
