from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


class UserCreate(BaseModel):
    """Schema for registering a new user."""
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=6, description="Password must be at least 6 characters")
    display_name: Optional[str] = Field(None, max_length=100)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email format")
        return v


class UserRead(BaseModel):
    """Safe schema for returning user profile without sensitive fields."""
    id: int
    email: str
    display_name: Optional[str] = None
    is_active: bool
    created_at: datetime
    default_household_id: Optional[int] = None
    default_household_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    """Schema for user credentials during JSON login."""
    email: str
    password: str


class TokenResponse(BaseModel):
    """Schema for returning JWT access token."""
    access_token: str
    token_type: str = "bearer"


class StagingFixtureCleanupRead(BaseModel):
    deleted_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    skipped_user_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def skipped_count_matches_identifiers(self):
        if self.skipped_count != len(self.skipped_user_ids):
            raise ValueError("Skipped fixture count must match reported user identifiers")
        if len(self.skipped_user_ids) != len(set(self.skipped_user_ids)):
            raise ValueError("Skipped fixture user identifiers must be unique")
        return self
