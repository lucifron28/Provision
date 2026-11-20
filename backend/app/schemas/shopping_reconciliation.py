from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.ingredients import StrictSchema
from app.schemas.product import ProductCreate


MAX_INVENTORY_AMOUNT = Decimal("99999999.99")


class PurchasedItemResolution(StrictSchema):
    shopping_item_id: int = Field(gt=0)
    expected_updated_at: datetime
    action: Literal["add", "exclude"]
    product_id: int | None = Field(default=None, gt=0)
    new_product: ProductCreate | None = None
    quantity: Decimal | None = Field(
        default=None,
        gt=0,
        le=MAX_INVENTORY_AMOUNT,
        max_digits=10,
        decimal_places=2,
    )
    inventory_unit: str | None = Field(default=None, min_length=1, max_length=50)
    storage_location_id: int | None = Field(default=None, gt=0)
    expiration_date: date | None = None
    unit_price: Decimal | None = Field(
        default=None,
        ge=0,
        le=MAX_INVENTORY_AMOUNT,
        max_digits=10,
        decimal_places=2,
    )

    @field_validator("quantity", "unit_price")
    @classmethod
    def finite_amounts(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("Inventory amounts must be finite")
        return value

    @field_validator("inventory_unit")
    @classmethod
    def clean_unit(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Inventory unit cannot be blank")
        return value

    @field_validator("expected_updated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Expected shopping item timestamp must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_action_fields(self) -> "PurchasedItemResolution":
        if self.action == "exclude":
            if any(
                value is not None
                for value in (
                    self.product_id,
                    self.new_product,
                    self.quantity,
                    self.inventory_unit,
                    self.storage_location_id,
                    self.expiration_date,
                    self.unit_price,
                )
            ):
                raise ValueError("Exclude resolutions cannot include inventory details")
            return self

        if (self.product_id is None) == (self.new_product is None):
            raise ValueError("Provide exactly one existing product or new product")
        if self.quantity is None or self.inventory_unit is None:
            raise ValueError("Adding an item requires its actual quantity and unit")
        if self.new_product is not None and not (self.new_product.unit or "").strip():
            raise ValueError("New products require an explicit inventory unit")
        if self.new_product is not None and self.inventory_unit.casefold() != self.new_product.unit.strip().casefold():
            raise ValueError("Inventory unit must match the new product unit")
        return self


class ReconcilePurchasedItemsRequest(StrictSchema):
    idempotency_key: str = Field(min_length=8, max_length=128)
    items: list[PurchasedItemResolution] = Field(min_length=1, max_length=50)

    @field_validator("idempotency_key")
    @classmethod
    def clean_idempotency_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Idempotency key cannot be blank")
        return value

    @model_validator(mode="after")
    def unique_item_ids(self) -> "ReconcilePurchasedItemsRequest":
        ids = [item.shopping_item_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("A shopping item can only be resolved once per request")
        return self


class ReconciledPurchasedItem(StrictSchema):
    shopping_item_id: int
    reconciliation_status: Literal["added_to_pantry", "excluded"]
    product_id: int | None = None
    product_name: str | None = None
    batch_id: int | None = None
    quantity: Decimal | None = None
    inventory_unit: str | None = None


class ReconcilePurchasedItemsRead(StrictSchema):
    items: list[ReconciledPurchasedItem]
    replayed: bool = False
