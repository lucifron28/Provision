from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.schemas.ingredients import IngredientRequirementInput, RecipeAvailabilityRead, RecipeAvailabilityRequest, StrictSchema


class IngredientSubstitution(StrictSchema):
    requirement_index: int = Field(ge=0, lt=200)
    replacement: IngredientRequirementInput


class FoodSafetyRequest(RecipeAvailabilityRequest):
    diner_user_ids: list[Annotated[int, Field(gt=0)]] | None = Field(default=None, min_length=1, max_length=100)
    substitutions: list[IngredientSubstitution] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_choices(self):
        indexes = [item.requirement_index for item in self.substitutions]
        if len(indexes) != len(set(indexes)) or any(index >= len(self.requirements) for index in indexes):
            raise ValueError("Substitutions must refer to distinct existing requirement indexes")
        if self.diner_user_ids is not None and len(self.diner_user_ids) != len(set(self.diner_user_ids)):
            raise ValueError("Diners must be distinct")
        return self


SafetyDecision = Literal["eligible", "blocked", "review_required"]


class IngredientSafetyRead(StrictSchema):
    requirement_index: int
    ingredient_id: int | None
    decision: SafetyDecision
    reasons: list[str]


class FoodSafetyRead(StrictSchema):
    decision: SafetyDecision
    reasons: list[str]
    ingredients: list[IngredientSafetyRead]
    availability: RecipeAvailabilityRead
    notice: str = "No known conflict is not a safety guarantee. Check actual labels and preparation."
