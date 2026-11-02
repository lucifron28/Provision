from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from app.schemas.ingredients import StrictSchema

Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
AllergenCode = Literal["milk", "egg", "fish", "crustacean_shellfish", "tree_nuts", "peanuts", "wheat", "soy", "sesame"]
AllergyStatus = Literal["NOT_PROVIDED", "NONE_DECLARED", "DECLARED"]


class FoodPreferencesInput(StrictSchema):
    preferred_cuisines: list[Tag] = Field(default_factory=lambda: ["Filipino"], max_length=30)
    preferred_regions: list[Tag] = Field(default_factory=list, max_length=30)
    dislikes: list[Tag] = Field(default_factory=list, max_length=100)
    diet_patterns: list[Literal["vegetarian", "vegan", "pescatarian", "halal", "no_pork", "gluten_free", "dairy_free"]] = Field(default_factory=list, max_length=7)
    ingredient_exclusions: list[Annotated[int, Field(gt=0)]] = Field(default_factory=list, max_length=100)
    heat_tolerance: Literal["mild", "medium", "hot", "no_preference"] = "no_preference"
    equipment: list[Tag] = Field(default_factory=list, max_length=50)
    max_cook_minutes: int | None = Field(default=None, gt=0, le=1440)
    meal_budget_php: Decimal | None = Field(default=None, ge=0, le=1000000, max_digits=9, decimal_places=2)
    preferred_language: Literal["en", "fil"] = "en"
    servings: Decimal = Field(default=Decimal("2"), gt=0, le=10000, max_digits=9, decimal_places=4)

    @model_validator(mode="after")
    def unique_selections(self):
        for field in ("preferred_cuisines", "preferred_regions", "dislikes", "diet_patterns", "ingredient_exclusions", "equipment"):
            values = getattr(self, field)
            normalized = [value.casefold() if isinstance(value, str) else value for value in values]
            if len(normalized) != len(set(normalized)):
                raise ValueError(f"{field} cannot contain duplicate selections")
        return self


class FoodAllergyInput(StrictSchema):
    allergen_code: AllergenCode | None = None
    custom_text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=180)] | None = None
    severity: Literal["mild", "moderate", "severe"] | None = None
    cross_contact_concern: bool = False
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None

    @model_validator(mode="after")
    def exactly_one_reference(self):
        if (self.allergen_code is None) == (self.custom_text is None):
            raise ValueError("Declare either a canonical allergen or custom text")
        return self


class FoodProfileInput(StrictSchema):
    expected_revision: int | None = Field(default=None, ge=1)
    preferences: FoodPreferencesInput = Field(default_factory=FoodPreferencesInput)
    allergy_status: AllergyStatus
    allergies: list[FoodAllergyInput] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def explicit_allergy_state(self):
        if (self.allergy_status == "DECLARED") != bool(self.allergies):
            raise ValueError("Only DECLARED profiles must contain allergy declarations")
        keys = [(item.allergen_code or item.custom_text).casefold() for item in self.allergies]
        if len(keys) != len(set(keys)):
            raise ValueError("Allergy declarations cannot be duplicated")
        return self


class FoodProfileRead(StrictSchema):
    scope: Literal["member", "household"]
    revision: int | None = None
    preferences: FoodPreferencesInput = Field(default_factory=FoodPreferencesInput)
    allergy_status: AllergyStatus = "NOT_PROVIDED"
    allergies: list[FoodAllergyInput] = Field(default_factory=list)
