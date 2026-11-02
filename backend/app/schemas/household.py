from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


HouseholdRoleValue = Literal["OWNER", "MEMBER"]


class HouseholdRead(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class HouseholdContextRead(HouseholdRead):
    role: HouseholdRoleValue


class HouseholdMembershipRead(HouseholdRead):
    role: HouseholdRoleValue
    is_default: bool


class HouseholdMemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int = Field(gt=0)
    role: HouseholdRoleValue = "MEMBER"


class HouseholdMemberUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: HouseholdRoleValue


class HouseholdMemberRead(BaseModel):
    user_id: int
    email: str
    display_name: str | None
    role: HouseholdRoleValue
    is_default: bool
    created_at: datetime
