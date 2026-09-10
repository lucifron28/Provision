from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.database import get_db
from app.models.event import InventoryEvent, EventType
from app.schemas.event import (
    ConsumeRequest,
    ConsumeResponse,
    DiscardRequest,
    AdjustmentRequest,
    InventoryEventRead,
)
from app.schemas.batch import InventoryBatchRead
from app.services.inventory import InventoryService

router = APIRouter()


@router.post("/consume", response_model=ConsumeResponse)
def consume_product(
    req: ConsumeRequest,
    db: Session = Depends(get_db),
):
    try:
        return InventoryService.consume_product_fefo(db, req)
    except ValueError as e:
        detail = str(e)
        status_code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail)


@router.post("/batches/{batch_id}/discard", response_model=InventoryBatchRead)
def discard_batch(
    batch_id: int,
    req: DiscardRequest,
    db: Session = Depends(get_db),
):
    try:
        return InventoryService.discard_batch(db, batch_id, req)
    except ValueError as e:
        detail = str(e)
        status_code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail)


@router.post("/batches/{batch_id}/adjust", response_model=InventoryBatchRead)
def adjust_batch(
    batch_id: int,
    req: AdjustmentRequest,
    db: Session = Depends(get_db),
):
    try:
        return InventoryService.adjust_batch(db, batch_id, req)
    except ValueError as e:
        detail = str(e)
        status_code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail)


@router.get("/events", response_model=List[InventoryEventRead])
def list_inventory_events(
    batch_id: Optional[int] = Query(None, description="Filter by batch ID"),
    event_type: Optional[EventType] = Query(None, description="Filter by event type"),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    stmt = select(InventoryEvent)
    if batch_id is not None:
        stmt = stmt.where(InventoryEvent.batch_id == batch_id)
    if event_type is not None:
        stmt = stmt.where(InventoryEvent.event_type == event_type)

    stmt = stmt.order_by(InventoryEvent.occurred_at.desc(), InventoryEvent.id.desc()).offset(skip).limit(limit)
    return db.scalars(stmt).all()
