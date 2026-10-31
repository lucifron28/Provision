from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from app.models.leftover import LeftoverEventType
from app.schemas.ingredients import StrictSchema
from app.services.units import normalize_unit


LeftoverQuantity = Annotated[
    Decimal,
    Field(gt=0, le=Decimal("99999999.999999"), max_digits=14, decimal_places=6),
]
PortionCount = Annotated[
    Decimal,
    Field(gt=0, le=Decimal("99999999.9999"), max_digits=12, decimal_places=4),
]
LeftoverUnit = Literal["g", "kg", "ml", "l", "count", "portion"]
LeftoverName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=180)]


def _unit(value: str) -> LeftoverUnit:
    if value.strip().casefold() == "portion":
        return "portion"
    return normalize_unit(value)


class LeftoverCreate(StrictSchema):
    name: LeftoverName
    recipe_id: int | None = Field(default=None, gt=0)
    recipe_revision: int | None = Field(default=None, ge=1)
    cooking_session_id: int | None = Field(default=None, gt=0)
    storage_location_id: int | None = Field(default=None, gt=0)
    prepared_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    use_by_date: date | None = None
    use_by_date_verified: bool = False
    quantity: LeftoverQuantity
    unit: LeftoverUnit
    portions: PortionCount | None = None

    @field_validator("prepared_at")
    @classmethod
    def aware_prepared_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("prepared_at must include a timezone")
        if value.astimezone(timezone.utc) > datetime.now(timezone.utc):
            raise ValueError("prepared_at cannot be in the future")
        return value

    @field_validator("quantity", "portions")
    @classmethod
    def finite_quantities(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("Leftover quantities must be finite")
        return value

    @field_validator("unit", mode="before")
    @classmethod
    def normalize_unit(cls, value: str) -> LeftoverUnit:
        return _unit(value)

    @model_validator(mode="after")
    def verified_and_pinned_dates(self):
        if (self.use_by_date is None) != (not self.use_by_date_verified):
            raise ValueError("A use-by date requires explicit user verification")
        if (self.recipe_id is None) != (self.recipe_revision is None):
            raise ValueError("recipe_id and recipe_revision must be provided together")
        return self


class LeftoverUpdate(StrictSchema):
    expected_revision: int = Field(ge=1)
    name: LeftoverName | None = None
    storage_location_id: int | None = Field(default=None, gt=0)
    use_by_date: date | None = None
    use_by_date_verified: bool | None = None

    @model_validator(mode="after")
    def validate_patch(self):
        if not (set(self.model_fields_set) - {"expected_revision"}):
            raise ValueError("At least one leftover field must be updated")
        date_fields = {"use_by_date", "use_by_date_verified"}
        if self.model_fields_set & date_fields and not date_fields <= self.model_fields_set:
            raise ValueError("Update use_by_date and its verification together")
        if "use_by_date" in self.model_fields_set:
            if (self.use_by_date is None) == bool(self.use_by_date_verified):
                raise ValueError("A use-by date requires explicit user verification")
        return self


class LeftoverDispositionInput(StrictSchema):
    expected_revision: int = Field(ge=1)
    quantity: LeftoverQuantity
    portions: PortionCount | None = None
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)] | None = None

    @field_validator("quantity", "portions")
    @classmethod
    def finite_quantities(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("Leftover quantities must be finite")
        return value


class LeftoverEventRead(StrictSchema):
    id: int
    event_type: LeftoverEventType
    quantity: Decimal
    unit: str
    portions: Decimal | None
    occurred_at: datetime
    reason: str | None = None


class LeftoverRead(StrictSchema):
    id: int
    household_id: int
    name: str
    recipe_id: int | None
    recipe_revision: int | None
    cooking_session_id: int | None
    storage_location_id: int | None
    prepared_at: datetime
    use_by_date: date | None
    use_by_date_verified: bool
    quantity: Decimal
    remaining_quantity: Decimal
    unit: str
    portions: Decimal | None
    remaining_portions: Decimal | None
    revision: int
    created_by_user_id: int | None
    archived_at: datetime | None
    is_expired: bool
    events: list[LeftoverEventRead] = Field(default_factory=list)


class LeftoverDispositionRead(StrictSchema):
    leftover: LeftoverRead
    event: LeftoverEventRead
