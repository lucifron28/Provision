from datetime import date, datetime, timezone
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import select, func, nulls_last

from app.models.product import Product
from app.models.batch import InventoryBatch
from app.models.event import InventoryEvent, EventType
from app.schemas.event import (
    ConsumeRequest,
    ConsumeResponse,
    BatchDeduction,
    DiscardRequest,
    AdjustmentRequest,
)


class InventoryService:
    @staticmethod
    def consume_product_fefo(db: Session, req: ConsumeRequest) -> ConsumeResponse:
        """
        Consumes stock of a product using First Expired, First Out (FEFO).
        Prefers batches with the earliest expiration date.
        If expiration date is null or identical, tie-breaks by purchased_at ASC.
        """
        product = db.get(Product, req.product_id)
        if not product:
            raise ValueError(f"Product with ID {req.product_id} not found")

        # Query all active batches for this product
        stmt = (
            select(InventoryBatch)
            .where(
                InventoryBatch.product_id == req.product_id,
                InventoryBatch.remaining_quantity > 0,
            )
            .order_by(
                nulls_last(InventoryBatch.expiration_date.asc()),
                InventoryBatch.purchased_at.asc(),
                InventoryBatch.id.asc(),
            )
        )
        active_batches = db.scalars(stmt).all()

        total_available = sum(b.remaining_quantity for b in active_batches)
        if total_available < req.quantity:
            raise ValueError(
                f"Insufficient inventory for '{product.name}': requested {req.quantity}, but only {total_available} available"
            )

        remaining_needed = float(req.quantity)
        deductions: List[BatchDeduction] = []
        now = datetime.now(timezone.utc)

        for batch in active_batches:
            if remaining_needed <= 0:
                break

            available_in_batch = float(batch.remaining_quantity)
            deduct_amount = min(available_in_batch, remaining_needed)

            # Update batch quantity
            batch.remaining_quantity = float(batch.remaining_quantity) - deduct_amount
            remaining_needed -= deduct_amount

            # Record CONSUMED event
            event = InventoryEvent(
                batch_id=batch.id,
                event_type=EventType.CONSUMED,
                quantity=deduct_amount,
                occurred_at=now,
                reason=req.reason,
                notes=req.notes,
            )
            db.add(event)

            deductions.append(
                BatchDeduction(
                    batch_id=batch.id,
                    quantity_deducted=deduct_amount,
                    remaining_in_batch=float(batch.remaining_quantity),
                    expiration_date=batch.expiration_date,
                )
            )

        db.commit()

        # Calculate new total stock
        new_total_stock = sum(float(b.remaining_quantity) for b in active_batches)

        return ConsumeResponse(
            product_id=product.id,
            requested_quantity=req.quantity,
            total_consumed=req.quantity,
            batches_deducted=deductions,
            new_total_stock=new_total_stock,
        )

    @staticmethod
    def discard_batch(db: Session, batch_id: int, req: DiscardRequest) -> InventoryBatch:
        """
        Discards the entire remaining contents of a batch (e.g. spoilage, past expiration).
        Records a DISCARDED or EXPIRED event.
        """
        batch = db.get(InventoryBatch, batch_id)
        if not batch:
            raise ValueError(f"Inventory batch with ID {batch_id} not found")

        current_qty = float(batch.remaining_quantity)
        if current_qty <= 0:
            raise ValueError(f"Inventory batch {batch_id} has no remaining quantity to discard")

        # Determine if event should be marked EXPIRED or DISCARDED
        today = date.today()
        event_type = EventType.DISCARDED
        if batch.expiration_date and batch.expiration_date < today:
            event_type = EventType.EXPIRED

        batch.remaining_quantity = 0.0

        event = InventoryEvent(
            batch_id=batch.id,
            event_type=event_type,
            quantity=current_qty,
            occurred_at=datetime.now(timezone.utc),
            reason=req.reason,
            notes=req.notes,
        )
        db.add(event)
        db.commit()
        db.refresh(batch)
        return batch

    @staticmethod
    def adjust_batch(db: Session, batch_id: int, req: AdjustmentRequest) -> InventoryBatch:
        """
        Performs an inventory reconciliation count adjustment and logs the discrepancy.
        """
        batch = db.get(InventoryBatch, batch_id)
        if not batch:
            raise ValueError(f"Inventory batch with ID {batch_id} not found")

        old_qty = float(batch.remaining_quantity)
        new_qty = float(req.new_remaining_quantity)
        delta = new_qty - old_qty

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
        db.commit()
        db.refresh(batch)
        return batch
