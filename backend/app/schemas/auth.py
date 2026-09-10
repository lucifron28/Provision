from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator


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

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    """Schema for user credentials during JSON login."""
    email: str
    password: str


class TokenResponse(BaseModel):
    """Schema for returning JWT access token."""
    access_token: str
    token_type: str = "bearer"
