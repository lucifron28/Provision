from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class StorageLocationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Location name, e.g. Pantry, Refrigerator")
    description: Optional[str] = Field(None, description="Optional description of location/shelf")


class StorageLocationCreate(StorageLocationBase):
    pass


class StorageLocationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None


class StorageLocationRead(StorageLocationBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
