from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.database import get_db
from app.models.location import StorageLocation
from app.schemas.location import (
    StorageLocationCreate,
    StorageLocationUpdate,
    StorageLocationRead,
)

router = APIRouter()


@router.get("/", response_model=List[StorageLocationRead])
def list_locations(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    stmt = select(StorageLocation).offset(skip).limit(limit).order_by(StorageLocation.name)
    return db.scalars(stmt).all()


@router.post("/", response_model=StorageLocationRead, status_code=status.HTTP_201_CREATED)
def create_location(
    location_in: StorageLocationCreate,
    db: Session = Depends(get_db),
):
    existing = db.scalar(
        select(StorageLocation).where(StorageLocation.name == location_in.name)
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Storage location with name '{location_in.name}' already exists",
        )
    location = StorageLocation(
        name=location_in.name,
        description=location_in.description,
    )
    db.add(location)
    db.commit()
    db.refresh(location)
    return location


@router.get("/{location_id}", response_model=StorageLocationRead)
def get_location(
    location_id: int,
    db: Session = Depends(get_db),
):
    location = db.get(StorageLocation, location_id)
    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage location not found",
        )
    return location


@router.patch("/{location_id}", response_model=StorageLocationRead)
def update_location(
    location_id: int,
    location_in: StorageLocationUpdate,
    db: Session = Depends(get_db),
):
    location = db.get(StorageLocation, location_id)
    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage location not found",
        )
    update_data = location_in.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"] != location.name:
        existing = db.scalar(
            select(StorageLocation).where(StorageLocation.name == update_data["name"])
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Storage location with name '{update_data['name']}' already exists",
            )
    for field, value in update_data.items():
        setattr(location, field, value)
    db.commit()
    db.refresh(location)
    return location


@router.delete("/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_location(
    location_id: int,
    db: Session = Depends(get_db),
):
    location = db.get(StorageLocation, location_id)
    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage location not found",
        )
    db.delete(location)
    db.commit()
    return None
