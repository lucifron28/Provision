from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import hmac
import json
from typing import List
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func, nulls_last

from app.core.time import household_today

from app.models.product import Product
from app.models.batch import InventoryBatch
from app.models.event import InventoryEvent, EventType
from app.models.inventory_action_idempotency import InventoryActionIdempotency
from app.schemas.batch import InventoryBatchRead
from app.schemas.event import (
    ConsumeRequest,
    ConsumeResponse,
    BatchDeduction,
    DiscardRequest,
    AdjustmentRequest,
)
from app.services.household_writes import bump_inventory_revision, lock_household_write


MEASURED_UNITS = {"g", "kg", "ml", "l"}


def _request_hash(request: ConsumeRequest | DiscardRequest | AdjustmentRequest) -> str:
    body = request.model_dump(mode="json", exclude={"idempotency_key"})
    encoded = json.dumps(body, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _get_replay(db: Session, household_id: int, actor_id: int | None, action_type: str,
                request: ConsumeRequest | DiscardRequest | AdjustmentRequest) -> dict | None:
    if request.idempotency_key is None:
        return None
    existing = db.scalar(
        select(InventoryActionIdempotency).where(
            InventoryActionIdempotency.household_id == household_id,
            InventoryActionIdempotency.idempotency_key == request.idempotency_key,
        )
    )
    if existing is None:
        return None
    request_hash = _request_hash(request)
    if (
        existing.actor_user_id != actor_id
        or existing.action_type != action_type
        or not hmac.compare_digest(existing.request_hash, request_hash)
    ):
        raise HTTPException(status_code=409, detail="IDEMPOTENCY_KEY_REUSED")
    return existing.response_snapshot


def _remember_result(db: Session, household_id: int, actor_id: int | None, action_type: str,
                     request: ConsumeRequest | DiscardRequest | AdjustmentRequest,
                     response_snapshot: dict) -> None:
    if request.idempotency_key is None:
        return
    db.add(
        InventoryActionIdempotency(
            household_id=household_id,
            actor_user_id=actor_id,
            action_type=action_type,
            idempotency_key=request.idempotency_key,
            request_hash=_request_hash(request),
            response_snapshot=response_snapshot,
        )
    )


def _require_whole_count(quantity: Decimal, unit: str | None, action: str) -> None:
    normalized_unit = unit.strip().casefold() if unit is not None else ""
    if normalized_unit not in MEASURED_UNITS and quantity != quantity.to_integral_value():
        raise ValueError(f"Count-based items require a whole-number {action} quantity")


def consume_batch_no_commit(
    db: Session,
    batch: InventoryBatch,
    quantity: Decimal,
    *,
    reason: str | None,
    notes: str | None = None,
    require_hundredths: bool = True,
    occurred_at: datetime | None = None,
) -> InventoryEvent:
    """Apply one locked batch deduction and ledger event without committing."""
    amount = Decimal(str(quantity))
    remaining = Decimal(str(batch.remaining_quantity))
    if not amount.is_finite() or amount <= 0 or amount > remaining:
        raise ValueError("Batch consumption must be positive and no greater than remaining stock")
    if require_hundredths:
        try:
            with_decimal_places = amount.quantize(Decimal("0.01"))
        except ArithmeticError as exc:
            raise ValueError("Batch consumption exceeds the stored precision") from exc
        if with_decimal_places != amount:
            raise ValueError("Batch consumption must be exactly representable in hundredths")

    batch.remaining_quantity = remaining - amount
    event = InventoryEvent(
        batch_id=batch.id,
        event_type=EventType.CONSUMED,
        quantity=amount,
        occurred_at=occurred_at or datetime.now(timezone.utc),
        reason=reason,
        notes=notes,
    )
    db.add(event)
    db.flush()
    return event


class InventoryService:
    @staticmethod
    def consume_product_fefo(
        db: Session, household_id: int, req: ConsumeRequest, actor_id: int | None = None
    ) -> ConsumeResponse:
        """
        Consumes stock of a product using First Expired, First Out (FEFO).
        Prefers batches with the earliest expiration date.
        If expiration date is null or identical, tie-breaks by purchased_at ASC.
        """
        lock_household_write(db, household_id, actor_id=actor_id)
        replay = _get_replay(db, household_id, actor_id, "consume", req)
        if replay is not None:
            return ConsumeResponse.model_validate(replay)
        product = db.scalar(
            select(Product).where(
                Product.id == req.product_id,
                Product.household_id == household_id,
            ).execution_options(populate_existing=True)
        )
        if not product:
            raise ValueError(f"Product with ID {req.product_id} not found")

        # Query all active batches for this product
        stmt = (
            select(InventoryBatch)
            .where(
                InventoryBatch.product_id == req.product_id,
                InventoryBatch.household_id == household_id,
                InventoryBatch.remaining_quantity > 0,
            )
            .order_by(
                nulls_last(InventoryBatch.expiration_date.asc()),
                InventoryBatch.purchased_at.asc(),
                InventoryBatch.id.asc(),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        active_batches = db.scalars(stmt).all()

        total_available = sum((Decimal(str(b.remaining_quantity)) for b in active_batches), Decimal("0"))
        quantity = Decimal(req.quantity)
        _require_whole_count(quantity, product.unit, "consumption")
        if total_available < quantity:
            raise ValueError(
                f"Insufficient inventory for '{product.name}': requested {req.quantity}, but only {total_available} available"
            )

        remaining_needed = quantity
        deductions: List[BatchDeduction] = []
        now = datetime.now(timezone.utc)

        for batch in active_batches:
            if remaining_needed <= 0:
                break

            available_in_batch = Decimal(str(batch.remaining_quantity))
            deduct_amount = min(available_in_batch, remaining_needed)

            consume_batch_no_commit(
                db,
                batch,
                Decimal(str(deduct_amount)),
                reason=req.reason,
                notes=req.notes,
                require_hundredths=True,
                occurred_at=now,
            )
            remaining_needed -= deduct_amount

            deductions.append(
                BatchDeduction(
                    batch_id=batch.id,
                    quantity_deducted=float(deduct_amount),
                    remaining_in_batch=float(batch.remaining_quantity),
                    expiration_date=batch.expiration_date,
                )
            )

        bump_inventory_revision(db, household_id)
        new_total_stock = sum((Decimal(str(b.remaining_quantity)) for b in active_batches), Decimal("0"))
        response = ConsumeResponse(
            product_id=product.id,
            requested_quantity=float(quantity),
            total_consumed=float(quantity),
            batches_deducted=deductions,
            new_total_stock=float(new_total_stock),
        )
        _remember_result(db, household_id, actor_id, "consume", req, response.model_dump(mode="json"))
        db.commit()
        return response

    @staticmethod
    def discard_batch(
        db: Session, household_id: int, batch_id: int, req: DiscardRequest, actor_id: int | None = None
    ) -> InventoryBatchRead:
        """
        Discards the entire remaining contents of a batch (e.g. spoilage, past expiration).
        Records a DISCARDED or EXPIRED event.
        """
        lock_household_write(db, household_id, actor_id=actor_id)
        replay = _get_replay(db, household_id, actor_id, "discard", req)
        if replay is not None:
            return InventoryBatchRead.model_validate(replay)
        batch = db.scalar(
            select(InventoryBatch).where(
                InventoryBatch.id == batch_id,
                InventoryBatch.household_id == household_id,
            ).with_for_update().execution_options(populate_existing=True)
        )
        if not batch:
            raise ValueError(f"Inventory batch with ID {batch_id} not found")

        current_qty = Decimal(str(batch.remaining_quantity))
        if current_qty <= 0:
            raise ValueError(f"Inventory batch {batch_id} has no remaining quantity to discard")
        if req.expected_updated_at is not None and batch.updated_at != req.expected_updated_at:
            raise HTTPException(status_code=409, detail="INVENTORY_BATCH_CHANGED")
        amount = Decimal(req.quantity) if req.quantity is not None else current_qty
        if amount > current_qty:
            raise ValueError("Discard quantity cannot exceed remaining stock")
        product = db.scalar(
            select(Product).where(
                Product.id == batch.product_id,
                Product.household_id == household_id,
            )
        )
        _require_whole_count(amount, product.unit if product else None, "discard")

        # Determine if event should be marked EXPIRED or DISCARDED
        today = household_today()
        event_type = EventType.DISCARDED
        if batch.expiration_date and batch.expiration_date < today:
            event_type = EventType.EXPIRED

        batch.remaining_quantity = current_qty - amount

        event = InventoryEvent(
            batch_id=batch.id,
            event_type=event_type,
            quantity=amount,
            occurred_at=datetime.now(timezone.utc),
            reason=req.reason,
            notes=req.notes,
        )
        db.add(event)
        bump_inventory_revision(db, household_id)
        db.flush()
        db.refresh(batch)
        response = InventoryBatchRead.model_validate(batch)
        _remember_result(db, household_id, actor_id, "discard", req, response.model_dump(mode="json"))
        db.commit()
        return response

    @staticmethod
    def adjust_batch(
        db: Session, household_id: int, batch_id: int, req: AdjustmentRequest, actor_id: int | None = None
    ) -> InventoryBatchRead:
        """
        Performs an inventory reconciliation count adjustment and logs the discrepancy.
        """
        lock_household_write(db, household_id, actor_id=actor_id)
        replay = _get_replay(db, household_id, actor_id, "adjust", req)
        if replay is not None:
            return InventoryBatchRead.model_validate(replay)
        batch = db.scalar(
            select(InventoryBatch).where(
                InventoryBatch.id == batch_id,
                InventoryBatch.household_id == household_id,
            ).with_for_update().execution_options(populate_existing=True)
        )
        if not batch:
            raise ValueError(f"Inventory batch with ID {batch_id} not found")

        if req.expected_updated_at is not None and batch.updated_at != req.expected_updated_at:
            raise HTTPException(status_code=409, detail="INVENTORY_BATCH_CHANGED")
        old_qty = Decimal(str(batch.remaining_quantity))
        new_qty = Decimal(req.new_remaining_quantity)
        product = db.scalar(
            select(Product).where(
                Product.id == batch.product_id,
                Product.household_id == household_id,
            )
        )
        _require_whole_count(new_qty, product.unit if product else None, "stock adjustment")
        delta = new_qty - old_qty
        if delta == 0:
            raise HTTPException(status_code=409, detail="BATCH_QUANTITY_UNCHANGED")

        batch.remaining_quantity = new_qty

        event = InventoryEvent(
            batch_id=batch.id,
            event_type=EventType.ADJUSTMENT,
            quantity=delta,
            occurred_at=datetime.now(timezone.utc),
            reason=f"{req.reason} (adjustment from {old_qty} to {new_qty}, delta: {delta:+.2f})",
            notes=req.notes,
        )
        db.add(event)
        bump_inventory_revision(db, household_id)
        db.flush()
        db.refresh(batch)
        response = InventoryBatchRead.model_validate(batch)
        _remember_result(db, household_id, actor_id, "adjust", req, response.model_dump(mode="json"))
        db.commit()
        return response
