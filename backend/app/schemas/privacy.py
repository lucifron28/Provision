from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.batch import InventoryBatchWithDetails
from app.schemas.event import InventoryEventRead
from app.schemas.location import StorageLocationRead
from app.schemas.product import ProductRead
from app.schemas.session import GrocerySessionRead
from app.schemas.shopping import ShoppingListItemRead
from app.schemas.preferences import FoodProfileRead
from app.schemas.recipe import RecipeRead, SavedRecipeRead
from app.schemas.meal_plan import MealPlanRead, MealPlanRevisionRead
from app.schemas.leftover import LeftoverRead
from app.schemas.cooking import CookingSessionRead


CONSENT_POLICY_VERSION = "2026-10-31"
CONSENT_NOTICE = (
    "When DeepSeek is enabled and every active household member consents, "
    "a recipe request can send the dish or search text you enter to DeepSeek. "
    "Do not include sensitive information in that text. Provision does not "
    "add pantry contents, allergy profiles, account identifiers, or shopping data. "
    "DeepSeek processes requests under its own privacy policy. You can revoke "
    "consent at any time; revocation blocks new household requests."
)


class ConsentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version: Literal["2026-10-31"]
    granted: bool


class ConsentRead(BaseModel):
    purpose: Literal["deepseek_recipes_v1"] = "deepseek_recipes_v1"
    policy_version: str = CONSENT_POLICY_VERSION
    granted: bool = False
    updated_at: datetime | None = None
    provider_enabled: bool = False
    notice: str = CONSENT_NOTICE


class AccountDeletion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: Literal["DELETE MY ACCOUNT"]
    password: str = Field(min_length=1, max_length=1024)


class AccountExportProfile(BaseModel):
    id: int
    email: str
    display_name: str | None
    is_active: bool
    created_at: datetime


class HouseholdExport(BaseModel):
    id: int
    name: str


class PantryExport(BaseModel):
    products: list[ProductRead]
    storage_locations: list[StorageLocationRead]
    grocery_sessions: list[GrocerySessionRead]
    inventory_batches: list[InventoryBatchWithDetails]
    inventory_events: list[InventoryEventRead]
    shopping_list_items: list[ShoppingListItemRead]


class AccountExport(BaseModel):
    schema_version: Literal[1] = 1
    exported_at: datetime
    account: AccountExportProfile
    household: HouseholdExport
    consent: ConsentRead
    pantry: PantryExport
    food_profiles: list[FoodProfileRead] = Field(default_factory=list)
    recipes: list[RecipeRead] = Field(default_factory=list)
    saved_recipes: list[SavedRecipeRead] = Field(default_factory=list)
    meal_plans: list[MealPlanRead] = Field(default_factory=list)
    meal_plan_history: dict[int, list[MealPlanRevisionRead]] = Field(default_factory=dict)
    leftovers: list[LeftoverRead] = Field(default_factory=list)
    cooking_sessions: list[CookingSessionRead] = Field(default_factory=list)
