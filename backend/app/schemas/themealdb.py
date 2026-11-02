"""Bounded, untrusted recipe text from an approved TheMealDB record."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StringConstraints, field_validator, model_validator

from app.schemas.ingredients import MAX_AMOUNT, StrictSchema
from app.schemas.deepseek import DeepSeekTokenUsage
from app.schemas.food_safety import FoodSafetyRead


class MealDBDiscoveryItem(StrictSchema):
    meal_id: Annotated[str, StringConstraints(pattern=r"^[0-9]{1,12}$")]
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    provider_url: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    original_source: Literal["not_yet_reviewed"] = "not_yet_reviewed"
    safety: Literal["review_required"] = "review_required"


class MealDBDiscoveryRead(StrictSchema):
    data_provider: Literal["TheMealDB"] = "TheMealDB"
    items: list[MealDBDiscoveryItem] = Field(max_length=20)


class ExactSourceMeasure(StrictSchema):
    amount: Decimal = Field(gt=0, le=MAX_AMOUNT, max_digits=14, decimal_places=6)
    unit: Literal["g", "kg", "ml", "l", "count"]


class MealDBIngredientText(StrictSchema):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=180)]
    source_measure: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]
    exact_measure: ExactSourceMeasure | None = None


class MealDBRecipeText(StrictSchema):
    meal_id: Annotated[str, StringConstraints(pattern=r"^[0-9]{1,12}$")]
    data_provider: Literal["TheMealDB"] = "TheMealDB"
    provider_url: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    ingredients: list[MealDBIngredientText] = Field(min_length=1, max_length=20)
    instructions: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=12000)]
    source_notices: dict[Annotated[str, StringConstraints(min_length=1, max_length=80)],
                         Annotated[str, StringConstraints(min_length=1, max_length=2000)]] = Field(default_factory=dict, max_length=10)
    api_source_id: int = Field(strict=True, gt=0)
    original_source_id: int = Field(strict=True, gt=0)
    api_source_revision: int = Field(strict=True, gt=0)
    original_source_revision: int = Field(strict=True, gt=0)
    source_url: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    content_digest: Annotated[str, StringConstraints(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")]
    untrusted_content: Literal[True] = True


class ConfirmedSourceMeasure(ExactSourceMeasure):
    ingredient_index: int = Field(strict=True, ge=0, lt=20)


class MealDBAssessmentInput(StrictSchema):
    source_digest: Annotated[str, StringConstraints(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")]
    confirmed_recipe_servings: Decimal = Field(gt=0, le=10000, max_digits=12, decimal_places=4)
    requested_servings: Decimal = Field(gt=0, le=10000, max_digits=12, decimal_places=4)
    allow_broader_web: StrictBool = False
    confirmed_measures: list[ConfirmedSourceMeasure] = Field(default_factory=list, max_length=20)

    @field_validator("confirmed_recipe_servings", "requested_servings")
    @classmethod
    def finite_servings(cls, value):
        if not value.is_finite():
            raise ValueError("Servings must be finite")
        return value

    @model_validator(mode="after")
    def unique_confirmed_measures(self):
        indexes = [item.ingredient_index for item in self.confirmed_measures]
        if len(indexes) != len(set(indexes)):
            raise ValueError("Confirmed measure indexes must be distinct")
        return self


class MealDBAssessmentRead(StrictSchema):
    source: MealDBRecipeText
    confirmed_recipe_servings: Decimal
    requested_servings: Decimal
    servings_basis: Literal["user_confirmed"] = "user_confirmed"
    confirmed_measures: list[ConfirmedSourceMeasure] = Field(default_factory=list, max_length=20)
    safety: FoodSafetyRead


class MealDBSourcePreviewRead(StrictSchema):
    source: MealDBRecipeText
    safety: Literal["review_required"] = "review_required"
    notice: str = "Review all ingredients, quantities, and allergens before cooking."


class MealDBAdaptedSteps(StrictSchema):
    steps: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]] = Field(min_length=1, max_length=30)


class MealDBAdaptationRead(StrictSchema):
    provenance: Literal["AI_ADAPTED"] = "AI_ADAPTED"
    source: MealDBRecipeText
    proposal: MealDBAdaptedSteps
    safety: Literal["review_required"] = "review_required"
    quantity_use: Literal["unverified_display_only"] = "unverified_display_only"
    notice: str = "Review all ingredients, quantities, allergens, and generated steps before cooking."
    model: str
    usage: DeepSeekTokenUsage
