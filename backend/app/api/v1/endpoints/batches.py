from datetime import date, datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, nulls_last, func

from app.core.database import get_db
from app.models.batch import InventoryBatch
from app.models.product import Product
from app.models.location import StorageLocation
from app.models.session import GrocerySession
from app.models.event import InventoryEvent, EventType
from app.schemas.batch import (
    InventoryBatchCreate,
    InventoryBatchUpdate,
    InventoryBatchRead,
    InventoryBatchWithDetails,
)

router = APIRouter()


@router.get("/", response_model=List[InventoryBatchWithDetails])
def list_batches(
    product_id: Optional[int] = Query(None, description="Filter by product ID"),
    storage_location_id: Optional[int] = Query(None, description="Filter by location ID"),
    active_only: bool = Query(True, description="Only return batches with remaining quantity > 0"),
    expiring_before: Optional[date] = Query(None, description="Filter batches expiring on or before this date"),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    stmt = (
        select(InventoryBatch)
        .options(
            joinedload(InventoryBatch.product),
            joinedload(InventoryBatch.storage_location),
        )
    )

    if product_id is not None:
        stmt = stmt.where(InventoryBatch.product_id == product_id)
    if storage_location_id is not None:
        stmt = stmt.where(InventoryBatch.storage_location_id == storage_location_id)
    if active_only:
        stmt = stmt.where(InventoryBatch.remaining_quantity > 0)
    if expiring_before is not None:
        stmt = stmt.where(InventoryBatch.expiration_date <= expiring_before)

    # Sort FEFO by default: earliest expiration first (nulls last), tie-break by purchased_at
    stmt = (
        stmt.order_by(
            nulls_last(InventoryBatch.expiration_date.asc()),
            InventoryBatch.purchased_at.asc(),
            InventoryBatch.id.asc(),
        )
        .offset(skip)
        .limit(limit)
    )

    return db.scalars(stmt).all()


@router.post("/", response_model=InventoryBatchWithDetails, status_code=status.HTTP_201_CREATED)
def create_batch(
    batch_in: InventoryBatchCreate,
    db: Session = Depends(get_db),
):
    # Verify Product exists
    product = db.get(Product, batch_in.product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {batch_in.product_id} not found",
        )

    # Verify StorageLocation if provided
    if batch_in.storage_location_id is not None:
        location = db.get(StorageLocation, batch_in.storage_location_id)
        if not location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Storage location with ID {batch_in.storage_location_id} not found",
            )

    # Verify GrocerySession if provided
    if batch_in.grocery_session_id is not None:
        session = db.get(GrocerySession, batch_in.grocery_session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Grocery session with ID {batch_in.grocery_session_id} not found",
            )

    purchased_at = batch_in.purchased_at or datetime.now(timezone.utc)

    batch = InventoryBatch(
        product_id=batch_in.product_id,
        storage_location_id=batch_in.storage_location_id,
        grocery_session_id=batch_in.grocery_session_id,
        purchased_at=purchased_at,
        expiration_date=batch_in.expiration_date,
        original_quantity=batch_in.original_quantity,
        remaining_quantity=batch_in.original_quantity,
        unit_price=batch_in.unit_price,
    )
    db.add(batch)
    db.flush()

    # Automatically record initial PURCHASED event
    purchase_event = InventoryEvent(
        batch_id=batch.id,
        event_type=EventType.PURCHASED,
        quantity=batch.original_quantity,
        occurred_at=purchased_at,
        reason="Initial purchase intake",
    )
    db.add(purchase_event)
    db.commit()

    # Reload with relationships
    stmt = (
        select(InventoryBatch)
        .options(
            joinedload(InventoryBatch.product),
            joinedload(InventoryBatch.storage_location),
        )
        .where(InventoryBatch.id == batch.id)
    )
    return db.scalar(stmt)


@router.get("/{batch_id}", response_model=InventoryBatchWithDetails)
def get_batch(
    batch_id: int,
    db: Session = Depends(get_db),
):
    stmt = (
        select(InventoryBatch)
        .options(
            joinedload(InventoryBatch.product),
            joinedload(InventoryBatch.storage_location),
        )
        .where(InventoryBatch.id == batch_id)
    )
    batch = db.scalar(stmt)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory batch with ID {batch_id} not found",
        )
    return batch


@router.patch("/{batch_id}", response_model=InventoryBatchWithDetails)
def update_batch(
    batch_id: int,
    batch_in: InventoryBatchUpdate,
    db: Session = Depends(get_db),
):
    stmt = (
        select(InventoryBatch)
        .options(
            joinedload(InventoryBatch.product),
            joinedload(InventoryBatch.storage_location),
        )
        .where(InventoryBatch.id == batch_id)
    )
    batch = db.scalar(stmt)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory batch with ID {batch_id} not found",
        )

    update_data = batch_in.model_dump(exclude_unset=True)

    if "storage_location_id" in update_data and update_data["storage_location_id"] is not None:
        location = db.get(StorageLocation, update_data["storage_location_id"])
        if not location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Storage location with ID {update_data['storage_location_id']} not found",
            )

    for field, value in update_data.items():
        setattr(batch, field, value)

    db.commit()
    db.refresh(batch)
    return batch


@router.delete("/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_batch(
    batch_id: int,
    db: Session = Depends(get_db),
):
    batch = db.get(InventoryBatch, batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory batch with ID {batch_id} not found",
        )

    event_count = db.scalar(
        select(func.count(InventoryEvent.id)).where(InventoryEvent.batch_id == batch_id)
    ) or 0
    if event_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete inventory batch with ID {batch_id}: it has {event_count} associated inventory event(s). Deletion blocked to preserve inventory history.",
        )

    db.delete(batch)
    db.commit()
    return None
