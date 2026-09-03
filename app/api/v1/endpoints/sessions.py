from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select

from app.core.database import get_db
from app.models.session import GrocerySession, GrocerySessionStatus
from app.models.product import Product
from app.models.location import StorageLocation
from app.models.batch import InventoryBatch
from app.models.event import InventoryEvent, EventType
from app.schemas.session import (
    GrocerySessionCreate,
    GrocerySessionUpdate,
    GrocerySessionRead,
    GrocerySessionWithBatches,
    CommitSessionRequest,
)

router = APIRouter()


def _get_session_with_batches(db: Session, session_id: int) -> GrocerySession:
    stmt = (
        select(GrocerySession)
        .options(joinedload(GrocerySession.batches))
        .where(GrocerySession.id == session_id)
    )
    session = db.scalar(stmt)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Grocery session with ID {session_id} not found",
        )
    return session


@router.get("/", response_model=List[GrocerySessionRead])
def list_sessions(
    status_filter: Optional[GrocerySessionStatus] = Query(None, alias="status", description="Filter by session status"),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    stmt = select(GrocerySession)
    if status_filter:
        stmt = stmt.where(GrocerySession.status == status_filter)
    stmt = stmt.order_by(GrocerySession.purchase_date.desc(), GrocerySession.id.desc()).offset(skip).limit(limit)
    return db.scalars(stmt).all()


@router.post("/", response_model=GrocerySessionRead, status_code=status.HTTP_201_CREATED)
def start_grocery_session(
    session_in: GrocerySessionCreate,
    db: Session = Depends(get_db),
):
    purchase_date = session_in.purchase_date or datetime.now(timezone.utc)
    session = GrocerySession(
        store_name=session_in.store_name,
        purchase_date=purchase_date,
        total_amount=session_in.total_amount,
        status=GrocerySessionStatus.DRAFT,
        notes=session_in.notes,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/{session_id}", response_model=GrocerySessionWithBatches)
def get_grocery_session(
    session_id: int,
    db: Session = Depends(get_db),
):
    return _get_session_with_batches(db, session_id)


@router.patch("/{session_id}", response_model=GrocerySessionRead)
def update_grocery_session(
    session_id: int,
    session_in: GrocerySessionUpdate,
    db: Session = Depends(get_db),
):
    session = db.get(GrocerySession, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Grocery session with ID {session_id} not found",
        )
    if session.status != GrocerySessionStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot edit session in '{session.status}' status",
        )

    update_data = session_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(session, field, value)

    db.commit()
    db.refresh(session)
    return session


@router.post("/{session_id}/commit", response_model=GrocerySessionWithBatches)
def commit_grocery_session(
    session_id: int,
    req: CommitSessionRequest,
    db: Session = Depends(get_db),
):
    session = _get_session_with_batches(db, session_id)
    if session.status == GrocerySessionStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot commit an already completed session",
        )
    if session.status == GrocerySessionStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot commit a cancelled session",
        )
    if session.status != GrocerySessionStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot commit session in status '{session.status}'",
        )

    purchased_at = session.purchase_date or datetime.now(timezone.utc)
    items_to_create = req.items or []

    # Validate all referenced products and storage locations upfront
    for item in items_to_create:
        product = db.get(Product, item.product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with ID {item.product_id} not found",
            )
        if item.storage_location_id:
            location = db.get(StorageLocation, item.storage_location_id)
            if not location:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Storage location with ID {item.storage_location_id} not found",
                )

    # Ingest validated items as inventory batches and initial PURCHASED events
    created_batches: List[InventoryBatch] = []
    for item in items_to_create:
        batch = InventoryBatch(
            product_id=item.product_id,
            storage_location_id=item.storage_location_id,
            grocery_session_id=session.id,
            purchased_at=purchased_at,
            expiration_date=item.expiration_date,
            original_quantity=item.quantity,
            remaining_quantity=item.quantity,
            unit_price=item.unit_price,
        )
        db.add(batch)
        db.flush()

        event = InventoryEvent(
            batch_id=batch.id,
            event_type=EventType.PURCHASED,
            quantity=batch.original_quantity,
            occurred_at=purchased_at,
            reason=f"Intake from {session.store_name} (Session #{session.id})",
        )
        db.add(event)
        created_batches.append(batch)

    session.status = GrocerySessionStatus.COMPLETED

    if req.total_amount is not None:
        session.total_amount = req.total_amount
    elif session.total_amount is None:
        # Calculate sum of items if available using Decimal
        computed_total = sum(
            (b.unit_price * Decimal(str(b.original_quantity)))
            for b in created_batches
            if b.unit_price is not None
        )
        if computed_total > Decimal("0.00"):
            session.total_amount = computed_total

    if req.notes:
        session.notes = req.notes

    db.commit()
    return _get_session_with_batches(db, session_id)


@router.delete("/{session_id}", response_model=GrocerySessionRead)
def cancel_grocery_session(
    session_id: int,
    db: Session = Depends(get_db),
):
    session = db.get(GrocerySession, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Grocery session with ID {session_id} not found",
        )
    if session.status == GrocerySessionStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel an already completed session",
        )
    if session.status == GrocerySessionStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is already cancelled",
        )

    session.status = GrocerySessionStatus.CANCELLED
    db.commit()
    db.refresh(session)
    return session
