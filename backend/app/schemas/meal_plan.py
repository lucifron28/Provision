"""Weekly schedule inputs and immutable plan-history reads."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.ingredients import StrictSchema


MealSlot = Literal["breakfast", "lunch", "dinner", "merienda"]


class MealPlanEntryInput(StrictSchema):
    meal_date: date
    slot: MealSlot
    position: int = Field(default=0, ge=0, le=9)
    recipe_id: int = Field(gt=0)
    recipe_revision: int = Field(ge=1)
    servings: Decimal = Field(gt=0, le=10000, max_digits=12, decimal_places=4)

    @field_validator("servings")
    @classmethod
    def finite_servings(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Servings must be finite")
        return value


class MealPlanReplaceRequest(StrictSchema):
    expected_revision: int | None = Field(default=None, ge=1)
    entries: list[MealPlanEntryInput] = Field(default_factory=list, max_length=140)

    @model_validator(mode="after")
    def distinct_positions(self):
        positions = [(entry.meal_date, entry.slot, entry.position) for entry in self.entries]
        if len(positions) != len(set(positions)):
            raise ValueError("A meal slot position cannot contain duplicate recipes")
        return self


class MealPlanEntryRead(StrictSchema):
    id: int
    meal_date: date
    slot: MealSlot
    position: int
    recipe_id: int
    recipe_revision: int
    recipe_title: str
    servings: Decimal


class MealPlanRead(StrictSchema):
    id: int
    week_start: date
    revision: int
    is_active: bool
    entries: list[MealPlanEntryRead] = Field(default_factory=list)


class MealPlanRevisionRead(StrictSchema):
    revision: int
    created_at: datetime
    created_by_user_id: int | None
    snapshot: dict
