from datetime import timedelta
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, func, or_

from app.core.database import get_db
from app.core.time import household_today
from app.models.product import Product
from app.models.batch import InventoryBatch
from app.models.location import StorageLocation
from app.models.event import InventoryEvent, EventType
from app.models.session import GrocerySession, GrocerySessionStatus
from app.schemas.analytics import (
    InventorySummaryItem,
    ExpiringSoonItem,
    LowStockItem,
    InventoryValuation,
    SpendingSummary,
    SpendingItem,
    WasteSummary,
    WasteItem,
    ProductPriceHistory,
    PriceHistoryPoint,
)

router = APIRouter()


@router.get("/inventory-summary", response_model=List[InventorySummaryItem])
def get_inventory_summary(db: Session = Depends(get_db)):
    """
    What food do I currently own? How much remains? Where is it stored?
    Returns current on-hand inventory grouped by product.
    """
    stmt = (
        select(InventoryBatch)
        .options(
            joinedload(InventoryBatch.product),
            joinedload(InventoryBatch.storage_location),
        )
        .where(InventoryBatch.remaining_quantity > 0)
    )
    batches = db.scalars(stmt).all()

    grouped = {}
    for b in batches:
        pid = b.product_id
        if pid not in grouped:
            grouped[pid] = {
                "product_id": pid,
                "product_name": b.product.name,
                "brand": b.product.brand,
                "category": b.product.category,
                "total_remaining": 0.0,
                "unit": b.product.unit,
                "active_batches_count": 0,
                "locations": set(),
            }
        grouped[pid]["total_remaining"] += float(b.remaining_quantity)
        grouped[pid]["active_batches_count"] += 1
        if b.storage_location:
            grouped[pid]["locations"].add(b.storage_location.name)

    return [
        InventorySummaryItem(
            product_id=v["product_id"],
            product_name=v["product_name"],
            brand=v["brand"],
            category=v["category"],
            total_remaining=round(v["total_remaining"], 2),
            unit=v["unit"],
            active_batches_count=v["active_batches_count"],
            locations=sorted(list(v["locations"])),
        )
        for v in grouped.values()
    ]


@router.get("/expiring-soon", response_model=List[ExpiringSoonItem])
def get_expiring_soon(
    days: int = Query(7, ge=1, description="Days horizon to look ahead"),
    db: Session = Depends(get_db),
):
    """
    Which items should I use first? What is expiring soon?
    Returns active batches expiring within the specified number of days.
    """
    today = household_today()
    max_date = today + timedelta(days=days)

    stmt = (
        select(InventoryBatch)
        .options(
            joinedload(InventoryBatch.product),
            joinedload(InventoryBatch.storage_location),
        )
        .where(
            InventoryBatch.remaining_quantity > 0,
            InventoryBatch.expiration_date.is_not(None),
            InventoryBatch.expiration_date <= max_date,
        )
        .order_by(InventoryBatch.expiration_date.asc())
    )
    batches = db.scalars(stmt).all()

    items = []
    for b in batches:
        days_left = (b.expiration_date - today).days
        items.append(
            ExpiringSoonItem(
                batch_id=b.id,
                product_id=b.product_id,
                product_name=b.product.name,
                brand=b.product.brand,
                remaining_quantity=float(b.remaining_quantity),
                unit=b.product.unit,
                expiration_date=b.expiration_date,
                days_until_expiration=days_left,
                storage_location=b.storage_location.name if b.storage_location else None,
            )
        )
    return items


@router.get("/low-stock", response_model=List[LowStockItem])
def get_low_stock(
    threshold: float = Query(1.0, ge=0, description="Threshold quantity"),
    db: Session = Depends(get_db),
):
    """
    What am I running low on? What should I buy next?
    """
    stock_subq = (
        select(
            InventoryBatch.product_id,
            func.coalesce(func.sum(InventoryBatch.remaining_quantity), 0.0).label("stock"),
        )
        .where(InventoryBatch.remaining_quantity > 0)
        .group_by(InventoryBatch.product_id)
        .subquery()
    )

    stmt = (
        select(
            Product,
            func.coalesce(stock_subq.c.stock, 0.0).label("current_stock"),
        )
        .outerjoin(stock_subq, Product.id == stock_subq.c.product_id)
    )

    rows = db.execute(stmt).all()
    results = []
    for product, current_stock in rows:
        if float(current_stock) <= threshold:
            results.append(
                LowStockItem(
                    product_id=product.id,
                    product_name=product.name,
                    brand=product.brand,
                    current_stock=float(current_stock),
                    unit=product.unit,
                )
            )
    return results


@router.get("/valuation", response_model=InventoryValuation)
def get_inventory_valuation(db: Session = Depends(get_db)):
    """
    How much is my current food inventory worth?
    Sums (remaining_quantity * unit_price) across active batches.
    """
    stmt = select(InventoryBatch).where(
        InventoryBatch.remaining_quantity > 0,
        InventoryBatch.unit_price.is_not(None),
    )
    batches = db.scalars(stmt).all()
    total_value = sum(
        (b.unit_price * Decimal(str(b.remaining_quantity)))
        for b in batches
        if b.unit_price is not None
    ) if batches else Decimal("0.00")

    active_batch_count = db.scalar(
        select(func.count(InventoryBatch.id)).where(InventoryBatch.remaining_quantity > 0)
    ) or 0
    active_prod_count = db.scalar(
        select(func.count(func.distinct(InventoryBatch.product_id))).where(InventoryBatch.remaining_quantity > 0)
    ) or 0

    return InventoryValuation(
        total_value=total_value.quantize(Decimal("0.01")),
        total_active_batches=active_batch_count,
        total_active_products=active_prod_count,
    )

@router.get("/spending", response_model=SpendingSummary)
def get_spending_summary(db: Session = Depends(get_db)):
    """
    How much have I spent on groceries?
    Aggregates completed grocery intake sessions.
    """
    sessions = db.scalars(
        select(GrocerySession)
        .where(GrocerySession.status == GrocerySessionStatus.COMPLETED)
        .order_by(GrocerySession.purchase_date.desc())
    ).all()

    total_spent = Decimal("0.00")
    transactions = []
    for s in sessions:
        amt = s.total_amount if s.total_amount is not None else Decimal("0.00")
        total_spent += amt
        transactions.append(
            SpendingItem(
                session_id=s.id,
                store_name=s.store_name,
                purchase_date=s.purchase_date,
                amount=amt,
            )
        )

    return SpendingSummary(
        total_spent=total_spent.quantize(Decimal("0.01")),
        sessions_count=len(sessions),
        recent_transactions=transactions,
    )

@router.get("/waste", response_model=WasteSummary)
def get_waste_summary(db: Session = Depends(get_db)):
    """
    What food am I wasting?
    Calculates quantity and estimated monetary loss from discarded and expired items.
    """
    stmt = (
        select(InventoryEvent)
        .options(
            joinedload(InventoryEvent.batch).joinedload(InventoryBatch.product)
        )
        .where(InventoryEvent.event_type.in_([EventType.DISCARDED, EventType.EXPIRED]))
        .order_by(InventoryEvent.occurred_at.desc())
    )
    events = db.scalars(stmt).all()
    total_qty = 0.0
    total_loss = Decimal("0.00")
    items = []

    for ev in events:
        qty = float(ev.quantity)
        total_qty += qty
        unit_price = ev.batch.unit_price
        loss = (Decimal(str(qty)) * unit_price) if unit_price is not None else None
        if loss is not None:
            total_loss += loss

        items.append(
            WasteItem(
                event_id=ev.id,
                product_name=ev.batch.product.name,
                event_type=ev.event_type.value,
                quantity=qty,
                unit=ev.batch.product.unit,
                occurred_at=ev.occurred_at,
                estimated_cost_wasted=loss.quantize(Decimal("0.01")) if loss is not None else None,
                reason=ev.reason,
            )
        )

    return WasteSummary(
        total_waste_events=len(events),
        total_quantity_wasted=round(total_qty, 2),
        total_financial_loss=total_loss.quantize(Decimal("0.01")),
        wasted_items=items,
    )

@router.get("/price-history/{product_id}", response_model=ProductPriceHistory)
def get_product_price_history(
    product_id: int,
    db: Session = Depends(get_db),
):
    """
    How have prices changed over time?
    Tracks historical purchase prices across all batches for a specific product.
    """
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {product_id} not found",
        )

    stmt = (
        select(InventoryBatch)
        .options(joinedload(InventoryBatch.grocery_session))
        .where(
            InventoryBatch.product_id == product_id,
            InventoryBatch.unit_price.is_not(None),
        )
        .order_by(InventoryBatch.purchased_at.asc())
    )
    batches = db.scalars(stmt).all()

    points = [
        PriceHistoryPoint(
            batch_id=b.id,
            purchased_at=b.purchased_at,
            unit_price=b.unit_price,
            store_name=b.grocery_session.store_name if b.grocery_session else None,
        )
        for b in batches
    ]

    return ProductPriceHistory(
        product_id=product.id,
        product_name=product.name,
        price_points=points,
    )
