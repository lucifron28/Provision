from typing import Literal

from pydantic import Field

from app.schemas.ingredients import StrictSchema
from app.schemas.deepseek import DeepSeekTokenUsage
from app.schemas.themealdb import MealDBAdaptedSteps


class WikibooksPreview(StrictSchema):
    title: Literal["Adobo Chicken (Philippine)"] = "Adobo Chicken (Philippine)"
    source_url: str
    publisher: Literal["Wikibooks contributors"] = "Wikibooks contributors"
    license_name: Literal["CC BY-SA 4.0"] = "CC BY-SA 4.0"
    license_url: Literal["https://creativecommons.org/licenses/by-sa/4.0/"] = "https://creativecommons.org/licenses/by-sa/4.0/"
    adapted: Literal[False] = False
    ingredients: list[str] = Field(min_length=1, max_length=50)
    preparation: list[str] = Field(min_length=1, max_length=50)
    untrusted_content: Literal[True] = True
    safety: Literal["review_required"] = "review_required"
    notice: str = "Review ingredients, quantities, allergens, and instructions before cooking."


class WikibooksAdaptation(StrictSchema):
    source: WikibooksPreview
    proposal: MealDBAdaptedSteps
    provenance: Literal["AI_ADAPTED"] = "AI_ADAPTED"
    adapted: Literal[True] = True
    adaptation_license_url: Literal["https://creativecommons.org/licenses/by-sa/4.0/"] = "https://creativecommons.org/licenses/by-sa/4.0/"
    safety: Literal["review_required"] = "review_required"
    notice: str = "Review generated steps, ingredients, quantities, and allergens before cooking."
    model: str
    usage: DeepSeekTokenUsage
