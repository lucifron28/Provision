from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from app.schemas.food_safety import FoodSafetyRead, IngredientSubstitution
from app.schemas.ingredients import IngredientRequirementInput, StrictSchema
from app.schemas.preferences import Tag

Region = Literal["Ilocano", "Bicolano", "Kapampangan", "Tagalog", "Visayan", "Mindanao", "region_unknown"]
Course = Literal["breakfast", "lunch", "dinner", "merienda", "dessert", "snack", "drink", "baon", "fiesta"]
DishType = Literal["ulam", "soup", "pancit", "rice", "gulay", "seafood", "grilled", "fried", "stew", "baked", "no_cook"]
Servings = Annotated[Decimal, Field(gt=0, le=10000, max_digits=12, decimal_places=4)]


class RecipeFields(StrictSchema):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    summary: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None
    cuisine: Tag = "Filipino"
    content_permission: Literal["NOT_DECLARED", "OWNED_OR_PERMISSION_GRANTED"] = "NOT_DECLARED"
    adapted_from_recipe_id: int | None = Field(default=None, gt=0)
    adapted_from_recipe_revision: int | None = Field(default=None, ge=1)
    ph_regions: list[Region] = Field(default_factory=lambda: ["region_unknown"], min_length=1, max_length=7)
    course_categories: list[Course] = Field(default_factory=list, max_length=9)
    dish_types: list[DishType] = Field(default_factory=list, max_length=11)
    difficulty: Literal["beginner", "intermediate", "advanced"] = "beginner"
    prep_minutes: int = Field(default=0, ge=0, le=1440)
    cook_minutes: int = Field(default=0, ge=0, le=1440)
    servings: Servings
    equipment: list[Tag] = Field(default_factory=list, max_length=50)
    spice_level: Literal["mild", "medium", "hot", "unknown"] = "unknown"
    instructions: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_classification(self):
        if (self.adapted_from_recipe_id is None) != (self.adapted_from_recipe_revision is None):
            raise ValueError("Adaptation parent recipe and revision must be provided together")
        for field in ("ph_regions", "course_categories", "dish_types", "equipment"):
            values = [item.casefold() for item in getattr(self, field)]
            if len(values) != len(set(values)):
                raise ValueError(f"{field} cannot contain duplicates")
        if "region_unknown" in self.ph_regions and len(self.ph_regions) > 1:
            raise ValueError("Unknown region cannot be combined with a claimed region")
        return self


class RecipeIngredientInput(IngredientRequirementInput):
    preparation: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    substitution_options: list[IngredientRequirementInput] = Field(default_factory=list, max_length=10)


class RecipeWrite(RecipeFields):
    expected_revision: int | None = Field(default=None, ge=1)
    ingredients: list[RecipeIngredientInput] = Field(min_length=1, max_length=200)


class RecipeIngredientRead(StrictSchema):
    ingredient_id: int | None
    display_name: str
    amount: Decimal
    unit: str
    required: bool
    preparation: str | None
    substitution_options: list[IngredientRequirementInput]


class RecipeRead(RecipeFields):
    id: int
    revision: int
    is_active: bool
    provenance: Literal["USER_ENTERED"] = "USER_ENTERED"
    ingredients: list[RecipeIngredientRead]


class RecipeEvaluationInput(StrictSchema):
    expected_recipe_revision: int = Field(ge=1)
    servings: Servings
    include_optional: bool = True
    diner_user_ids: list[Annotated[int, Field(gt=0)]] | None = Field(default=None, min_length=1, max_length=100)
    substitutions: list[IngredientSubstitution] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def unique_selections(self):
        indexes = [item.requirement_index for item in self.substitutions]
        if len(indexes) != len(set(indexes)):
            raise ValueError("Substitutions must target distinct recipe lines")
        if self.diner_user_ids is not None and len(self.diner_user_ids) != len(set(self.diner_user_ids)):
            raise ValueError("Diners must be distinct")
        return self


class SaveRecipeInput(StrictSchema):
    expected_revision: int | None = Field(default=None, ge=1)
    expected_recipe_revision: int = Field(ge=1)
    favorite: bool = False
    servings: Servings | None = None
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None


class SavedRecipeRead(StrictSchema):
    recipe_id: int
    recipe_revision: int
    revision: int
    is_saved: bool
    favorite: bool
    servings: Decimal | None
    notes: str | None


class RecipeEvaluationRead(StrictSchema):
    recipe_id: int
    recipe_revision: int
    included_requirement_indexes: list[int] = Field(default_factory=list)
    result: FoodSafetyRead
