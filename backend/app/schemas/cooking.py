from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.food_safety import FoodSafetyRead
from app.schemas.ingredients import StrictSchema
from app.schemas.leftover import LeftoverCreate, LeftoverRead
from app.services.units import normalize_unit


CookingServings = Annotated[
    Decimal,
    Field(gt=0, le=Decimal("10000"), max_digits=12, decimal_places=4),
]
CookingAmount = Annotated[
    Decimal,
    Field(gt=0, le=Decimal("99999999.999999"), max_digits=14, decimal_places=6),
]


class CookingAmountOverride(StrictSchema):
    requirement_index: int = Field(ge=0, lt=200)
    amount: CookingAmount
    unit: str = Field(min_length=1, max_length=24)

    @field_validator("amount")
    @classmethod
    def finite_amount(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Cooking amount must be finite")
        return value

    @field_validator("unit")
    @classmethod
    def known_unit(cls, value: str) -> str:
        return normalize_unit(value)


class CookingPreviewRequest(StrictSchema):
    recipe_id: int = Field(gt=0)
    expected_recipe_revision: int = Field(ge=1)
    servings: CookingServings
    include_optional: bool = False
    diner_user_ids: list[Annotated[int, Field(gt=0)]] | None = Field(
        default=None, min_length=1, max_length=100
    )
    actual_amount_overrides: list[CookingAmountOverride] = Field(
        default_factory=list, max_length=200
    )

    @model_validator(mode="after")
    def unique_selections(self):
        indexes = [item.requirement_index for item in self.actual_amount_overrides]
        if len(indexes) != len(set(indexes)):
            raise ValueError("Each recipe ingredient can have at most one amount override")
        if self.diner_user_ids is not None and len(self.diner_user_ids) != len(set(self.diner_user_ids)):
            raise ValueError("Diners must be distinct")
        return self

    @field_validator("servings")
    @classmethod
    def finite_servings(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Servings must be finite")
        return value


class CookingBatchAllocationRead(StrictSchema):
    batch_id: int
    product_id: int
    product_name: str
    native_quantity: Decimal
    native_unit: str
    ingredient_quantity: Decimal
    ingredient_unit: str
    storage_location_id: int | None = None
    storage_location_name: str | None = None
    expiration_date: date | None = None
    expiration_unknown: bool


class CookingRequirementRead(StrictSchema):
    requirement_indexes: list[int]
    ingredient_id: int
    canonical_name: str
    requested_quantity: Decimal
    unit: str
    optional: bool
    allocations: list[CookingBatchAllocationRead]


class CookingPreviewRead(StrictSchema):
    preview_id: str = Field(min_length=1, max_length=32768)
    expires_at: datetime
    recipe_id: int
    recipe_revision: int
    recipe_title: str
    servings: Decimal
    inventory_revision: int
    safety: FoodSafetyRead
    requirements: list[CookingRequirementRead]
    missing_expiry_batch_ids: list[int]


class CookingConfirmRequest(StrictSchema):
    preview_id: str = Field(min_length=1, max_length=32768)
    idempotency_key: str = Field(min_length=8, max_length=128)
    confirmation: Literal["RECORD COOKING"]
    record_history: Literal[True]
    acknowledged_missing_expiry_batch_ids: list[int] = Field(default_factory=list, max_length=500)
    leftovers: list[LeftoverCreate] = Field(default_factory=list, max_length=50)

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def clean_idempotency_key(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not 8 <= len(value) <= 128:
            raise ValueError("Idempotency key must contain 8 to 128 nonblank characters")
        return value

    @model_validator(mode="after")
    def unique_acknowledgements(self):
        if len(self.acknowledged_missing_expiry_batch_ids) != len(
            set(self.acknowledged_missing_expiry_batch_ids)
        ):
            raise ValueError("Missing-expiry batch acknowledgements must be distinct")
        if any(batch_id <= 0 for batch_id in self.acknowledged_missing_expiry_batch_ids):
            raise ValueError("Batch IDs must be positive")
        return self


class CookingConsumptionRead(StrictSchema):
    batch_id: int
    inventory_event_id: int
    ingredient_id: int
    ingredient_quantity: Decimal
    ingredient_unit: str


class CookingSessionRead(StrictSchema):
    id: int
    recipe_id: int
    recipe_revision: int
    servings: Decimal
    recorded_at: datetime
    inventory_revision: int
    consumptions: list[CookingConsumptionRead] = Field(default_factory=list)
    leftovers: list[LeftoverRead] = Field(default_factory=list)


class CookingConfirmRead(StrictSchema):
    session: CookingSessionRead
