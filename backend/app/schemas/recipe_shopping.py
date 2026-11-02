from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.food_safety import FoodSafetyRead
from app.schemas.ingredients import MAX_AMOUNT, StrictSchema
from app.schemas.shopping import ShoppingListItemRead


class RecipeShoppingPreviewRequest(StrictSchema):
    recipe_id: int = Field(gt=0)
    expected_recipe_revision: int = Field(ge=1)
    servings: Decimal = Field(gt=0, le=10000, max_digits=12, decimal_places=4)
    diner_user_ids: list[Annotated[int, Field(gt=0)]] | None = Field(
        default=None, min_length=1, max_length=100
    )
    include_optional: bool = False

    @field_validator("servings")
    @classmethod
    def finite_servings(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Servings must be finite")
        return value

    @model_validator(mode="after")
    def unique_diners(self):
        if self.diner_user_ids is not None and len(self.diner_user_ids) != len(set(self.diner_user_ids)):
            raise ValueError("Diners must be distinct")
        return self


class RecipeShoppingLine(StrictSchema):
    ingredient_id: int | None
    canonical_name: str | None
    display_name: str
    unit: str | None
    required_quantity: Decimal | None
    pantry_quantity: Decimal | None
    shortage: Decimal | None
    pending_quantity: Decimal | None
    target_quantity: Decimal | None
    additional_quantity: Decimal | None
    pending_item_ids: list[int] = Field(default_factory=list)
    covered_batch_ids: list[int] = Field(default_factory=list)
    status: Literal["ready", "review_required"]
    review_reasons: list[str] = Field(default_factory=list)


class UnlinkedShoppingItemReview(StrictSchema):
    item_id: int
    name: str
    quantity: float
    unit: str | None
    candidate_ingredient_ids: list[int] = Field(default_factory=list)
    reason: str


class RecipeShoppingPreviewRead(StrictSchema):
    preview_id: str
    expires_at: datetime
    recipe_id: int
    recipe_revision: int
    servings: Decimal
    include_optional: bool
    shopping_revision: int
    inventory_revision: int
    included_requirement_indexes: list[int] = Field(default_factory=list)
    safety: FoodSafetyRead
    lines: list[RecipeShoppingLine]
    unlinked_manual_items: list[UnlinkedShoppingItemReview] = Field(default_factory=list)


class RecipeShoppingAcceptedLine(StrictSchema):
    ingredient_id: int = Field(gt=0)
    target_quantity: Decimal = Field(gt=0, le=MAX_AMOUNT, max_digits=14, decimal_places=6)
    consolidate_existing: bool = False

    @field_validator("target_quantity")
    @classmethod
    def finite_target(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Target quantity must be finite")
        return value


class RecipeShoppingConfirmRequest(StrictSchema):
    preview_id: str = Field(min_length=1, max_length=4096)
    idempotency_key: str = Field(min_length=8, max_length=128)
    expected_revision: int = Field(ge=0)
    accepted_lines: list[RecipeShoppingAcceptedLine] = Field(default_factory=list, max_length=200)

    @field_validator("idempotency_key")
    @classmethod
    def clean_idempotency_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Idempotency key cannot be blank")
        return value

    @model_validator(mode="after")
    def unique_accepted_ingredients(self):
        ids = [line.ingredient_id for line in self.accepted_lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Accepted ingredients must be distinct")
        return self


class ShoppingItemDeletionSnapshot(StrictSchema):
    id: int
    name: str
    quantity: float
    unit: str | None
    product_id: int | None
    ingredient_id: int | None
    is_bought: bool
    notes: str | None
    origin_recipe_id: int | None
    origin_recipe_revision: int | None
    origin_plan_id: int | None = None
    origin_plan_revision: int | None = None


class ConsolidatedShoppingItems(StrictSchema):
    kept_item_id: int
    removed_items: list[ShoppingItemDeletionSnapshot]


class RecipeShoppingConfirmRead(StrictSchema):
    preview_id: str
    shopping_revision: int
    created: list[ShoppingListItemRead] = Field(default_factory=list)
    updated: list[ShoppingListItemRead] = Field(default_factory=list)
    unchanged: list[ShoppingListItemRead] = Field(default_factory=list)
    consolidated: list[ConsolidatedShoppingItems] = Field(default_factory=list)
