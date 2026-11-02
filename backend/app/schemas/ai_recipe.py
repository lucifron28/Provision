"""Untrusted AI-original recipe proposals; no inventory or publisher claims."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from app.schemas.food_safety import FoodSafetyRead
from app.schemas.ingredients import StrictSchema
from app.schemas.deepseek import DeepSeekTokenUsage


class AIRecipeIngredient(StrictSchema):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=180)]
    amount: Decimal = Field(gt=0, le=100000, max_digits=12, decimal_places=4)
    unit: Literal["g", "kg", "ml", "l", "count"]
    required: bool = True

    @field_validator("amount")
    @classmethod
    def finite_amount(cls, value):
        if not value.is_finite():
            raise ValueError("Ingredient amount must be finite")
        return value


class AIRecipeProposal(StrictSchema):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    servings: Decimal = Field(gt=0, le=100, max_digits=7, decimal_places=2)
    ingredients: list[AIRecipeIngredient] = Field(min_length=1, max_length=40)
    steps: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]] = Field(min_length=1, max_length=30)

    @field_validator("servings")
    @classmethod
    def finite_servings(cls, value):
        if not value.is_finite():
            raise ValueError("Servings must be finite")
        return value


class AIRecipeRequest(StrictSchema):
    dish: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    diner_user_ids: list[Annotated[int, Field(gt=0)]] | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def distinct_diners(self):
        if self.diner_user_ids is not None and len(self.diner_user_ids) != len(set(self.diner_user_ids)):
            raise ValueError("Diners must be distinct")
        return self


class AIRecipeRead(StrictSchema):
    provenance: Literal["AI_ORIGINAL"] = "AI_ORIGINAL"
    proposal: AIRecipeProposal
    safety: FoodSafetyRead
    model: str
    usage: DeepSeekTokenUsage
