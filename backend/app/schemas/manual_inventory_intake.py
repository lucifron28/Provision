from datetime import date, datetime
from decimal import Decimal

from pydantic import Field, field_validator, model_validator

from app.schemas.ingredients import StrictSchema
from app.schemas.product import ProductCreate


class ManualInventoryIntakeRequest(StrictSchema):
    idempotency_key: str = Field(min_length=8, max_length=128)
    product_id: int | None = Field(default=None, gt=0)
    new_product: ProductCreate | None = None
    storage_location_id: int | None = Field(default=None, gt=0)
    purchased_at: datetime | None = None
    expiration_date: date | None = None
    quantity: Decimal = Field(gt=0, le=Decimal("99999999.99"), max_digits=10, decimal_places=2)
    unit_price: Decimal | None = Field(
        default=None, ge=0, le=Decimal("99999999.99"), max_digits=10, decimal_places=2
    )

    @field_validator("idempotency_key")
    @classmethod
    def clean_idempotency_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Idempotency key cannot be blank")
        return value

    @field_validator("quantity", "unit_price")
    @classmethod
    def finite_amounts(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("Inventory amounts must be finite")
        return value

    @model_validator(mode="after")
    def exactly_one_product_source(self):
        if (self.product_id is None) == (self.new_product is None):
            raise ValueError("Provide exactly one existing product or new product")
        return self


class ManualInventoryIntakeRead(StrictSchema):
    product_id: int
    product_name: str
    unit: str | None
    batch_id: int
    quantity: float
    expiration_date: date | None
    storage_location_id: int | None
    replayed: bool = False
