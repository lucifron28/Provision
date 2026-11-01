"""Bounded, untrusted recipe text from an approved TheMealDB record."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.schemas.ingredients import StrictSchema
from app.schemas.deepseek import DeepSeekTokenUsage


class MealDBDiscoveryItem(StrictSchema):
    meal_id: Annotated[str, StringConstraints(pattern=r"^[0-9]{1,12}$")]
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    provider_url: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    original_source: Literal["not_yet_reviewed"] = "not_yet_reviewed"
    safety: Literal["review_required"] = "review_required"


class MealDBDiscoveryRead(StrictSchema):
    data_provider: Literal["TheMealDB"] = "TheMealDB"
    items: list[MealDBDiscoveryItem] = Field(max_length=20)


class MealDBIngredientText(StrictSchema):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=180)]
    source_measure: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]


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
    untrusted_content: Literal[True] = True


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
