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


CONSENT_POLICY_VERSION = "2026-10-30"


class ConsentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version: Literal["2026-10-30"]
    granted: bool


class ConsentRead(BaseModel):
    purpose: Literal["deepseek_recipes_v1"] = "deepseek_recipes_v1"
    policy_version: str = CONSENT_POLICY_VERSION
    granted: bool = False
    updated_at: datetime | None = None
    provider_enabled: bool = False


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
