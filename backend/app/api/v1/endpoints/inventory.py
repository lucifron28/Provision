from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.database import get_db
from app.api.v1.dependencies import get_current_household_id, get_current_household_id_for_write
from app.models.batch import InventoryBatch
from app.models.event import InventoryEvent, EventType
from app.models.user import User
from app.schemas.event import (
    ConsumeRequest,
    ConsumeResponse,
    DiscardRequest,
    AdjustmentRequest,
    InventoryEventRead,
)
from app.schemas.batch import InventoryBatchRead
from app.services.inventory import InventoryService
from app.schemas.manual_inventory_intake import (
    ManualInventoryIntakeRead,
    ManualInventoryIntakeRequest,
)
from app.services.manual_inventory_intake import create_manual_inventory_intake
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()


@router.post(
    "/manual-intake",
    response_model=ManualInventoryIntakeRead,
    status_code=status.HTTP_201_CREATED,
)
def create_manual_intake(
    request: ManualInventoryIntakeRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    household_id: int = Depends(get_current_household_id_for_write),
    db: Session = Depends(get_db),
):
    result = create_manual_inventory_intake(db, household_id, current_user.id, request)
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return result


@router.post("/consume", response_model=ConsumeResponse)
def consume_product(
    req: ConsumeRequest,
    current_user: User = Depends(get_current_user),
    household_id: int = Depends(get_current_household_id_for_write),
    db: Session = Depends(get_db),
):
    try:
        return InventoryService.consume_product_fefo(db, household_id, req, actor_id=current_user.id)
    except ValueError as e:
        detail = str(e)
        status_code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail)


@router.post("/batches/{batch_id}/discard", response_model=InventoryBatchRead)
def discard_batch(
    batch_id: int,
    req: DiscardRequest,
    current_user: User = Depends(get_current_user),
    household_id: int = Depends(get_current_household_id_for_write),
    db: Session = Depends(get_db),
):
    try:
        return InventoryService.discard_batch(db, household_id, batch_id, req, actor_id=current_user.id)
    except ValueError as e:
        detail = str(e)
        status_code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail)


@router.post("/batches/{batch_id}/adjust", response_model=InventoryBatchRead)
def adjust_batch(
    batch_id: int,
    req: AdjustmentRequest,
    current_user: User = Depends(get_current_user),
    household_id: int = Depends(get_current_household_id_for_write),
    db: Session = Depends(get_db),
):
    try:
        return InventoryService.adjust_batch(db, household_id, batch_id, req, actor_id=current_user.id)
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
    household_id: int = Depends(get_current_household_id),
    db: Session = Depends(get_db),
):
    stmt = (
        select(InventoryEvent)
        .join(InventoryBatch, InventoryBatch.id == InventoryEvent.batch_id)
        .where(InventoryBatch.household_id == household_id)
    )
    if batch_id is not None:
        stmt = stmt.where(InventoryEvent.batch_id == batch_id)
    if event_type is not None:
        stmt = stmt.where(InventoryEvent.event_type == event_type)

    stmt = stmt.order_by(InventoryEvent.occurred_at.desc(), InventoryEvent.id.desc()).offset(skip).limit(limit)
    return db.scalars(stmt).all()
