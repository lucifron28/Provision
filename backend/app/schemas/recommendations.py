from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.schemas.food_safety import FoodSafetyRead
from app.schemas.ingredients import StrictSchema
from app.schemas.preferences import Tag
from app.schemas.recipe import Course, RecipeRead, Region, Servings


class RecommendationInput(StrictSchema):
    servings: Servings | None = None
    diner_user_ids: list[Annotated[int, Field(gt=0)]] | None = Field(default=None, min_length=1, max_length=100)
    mode: Literal["all", "cook_now", "almost_there"] = "all"
    priority: Literal["pantry_first", "quick", "preferred_cuisine"] = "pantry_first"
    query: Tag | None = None
    cuisine: Tag | None = None
    ph_region: Region | None = None
    course: Course | None = None
    max_total_minutes: int | None = Field(default=None, gt=0, le=2880)
    available_equipment: list[Tag] | None = Field(default=None, max_length=50)
    max_missing_ingredients: int = Field(default=3, ge=1, le=20)
    expiry_window_days: int = Field(default=3, ge=1, le=30)
    limit: int = Field(default=20, ge=1, le=100)
    candidate_limit: int = Field(default=100, ge=1, le=200)
    candidate_offset: int = Field(default=0, ge=0, le=100000)

    @model_validator(mode="after")
    def unique_diners(self):
        if self.diner_user_ids is not None and len(self.diner_user_ids) != len(set(self.diner_user_ids)):
            raise ValueError("Diners must be distinct")
        return self


class RecipeRecommendation(StrictSchema):
    recipe: RecipeRead
    evaluation: FoodSafetyRead
    coverage: Decimal
    missing_ingredient_count: int
    near_expiry_batch_count: int
    preference_match: bool


class RecommendationRead(StrictSchema):
    items: list[RecipeRecommendation]
    candidates_evaluated: int
    has_more_candidates: bool
    excluded_blocked: int
    excluded_review_required: int
    excluded_unknown_quantities: int
    provider_enabled: Literal[False] = False
