"""Preview and confirmation contracts for aggregate weekly-plan shopping."""

from datetime import date, datetime
from typing import Annotated

from pydantic import Field, model_validator

from app.schemas.food_safety import FoodSafetyRead
from app.schemas.ingredients import StrictSchema
from app.schemas.meal_plan import MealPlanEntryRead
from app.schemas.recipe_shopping import (
    ConsolidatedShoppingItems,
    RecipeShoppingAcceptedLine,
    RecipeShoppingConfirmRequest,
    RecipeShoppingLine,
    UnlinkedShoppingItemReview,
)
from app.schemas.shopping import ShoppingListItemRead


class PlanShoppingPreviewRequest(StrictSchema):
    plan_id: int = Field(gt=0)
    expected_plan_revision: int = Field(ge=1)
    diner_user_ids: list[Annotated[int, Field(gt=0)]] | None = Field(
        default=None, min_length=1, max_length=100
    )
    include_optional: bool = False

    @model_validator(mode="after")
    def unique_diners(self):
        if self.diner_user_ids is not None and len(self.diner_user_ids) != len(set(self.diner_user_ids)):
            raise ValueError("Diners must be distinct")
        return self


class PlanShoppingPreviewRead(StrictSchema):
    preview_id: str
    expires_at: datetime
    plan_id: int
    plan_revision: int
    week_start: date
    shopping_revision: int
    inventory_revision: int
    entries: list[MealPlanEntryRead] = Field(default_factory=list, max_length=140)
    safety: FoodSafetyRead
    lines: list[RecipeShoppingLine]
    unlinked_manual_items: list[UnlinkedShoppingItemReview] = Field(default_factory=list)


class PlanShoppingConfirmRequest(RecipeShoppingConfirmRequest):
    accepted_lines: list[RecipeShoppingAcceptedLine] = Field(default_factory=list, max_length=200)


class PlanShoppingConfirmRead(StrictSchema):
    preview_id: str
    plan_id: int
    plan_revision: int
    shopping_revision: int
    created: list[ShoppingListItemRead] = Field(default_factory=list)
    updated: list[ShoppingListItemRead] = Field(default_factory=list)
    unchanged: list[ShoppingListItemRead] = Field(default_factory=list)
    consolidated: list[ConsolidatedShoppingItems] = Field(default_factory=list)
