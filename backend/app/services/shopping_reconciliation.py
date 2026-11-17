import hashlib
import hmac
import json
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.batch import InventoryBatch
from app.models.event import EventType, InventoryEvent
from app.models.location import StorageLocation
from app.models.product import Product, ProductSource
from app.models.shopping import ShoppingListItem
from app.models.shopping_reconciliation import ShoppingPantryReconciliationIdempotency
from app.schemas.shopping_reconciliation import (
    ReconcilePurchasedItemsRead,
    ReconcilePurchasedItemsRequest,
    ReconciledPurchasedItem,
)
from app.services.household_writes import bump_inventory_revision, bump_shopping_revision, lock_household_write


def _request_hash(request: ReconcilePurchasedItemsRequest) -> str:
    body = request.model_dump(mode="json", exclude={"idempotency_key"})
    encoded = json.dumps(body, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _same_unit(left: str | None, right: str | None) -> bool:
    return bool(left and right and left.strip().casefold() == right.strip().casefold())


def reconcile_purchased_items(
    db: Session,
    household_id: int,
    actor_id: int,
    request: ReconcilePurchasedItemsRequest,
) -> ReconcilePurchasedItemsRead:
    """Apply a reviewed shopping-to-pantry batch atomically and replay exact retries."""
    lock_household_write(db, household_id, actor_id=actor_id)
    request_hash = _request_hash(request)
    existing = db.scalar(
        select(ShoppingPantryReconciliationIdempotency).where(
            ShoppingPantryReconciliationIdempotency.household_id == household_id,
            ShoppingPantryReconciliationIdempotency.idempotency_key == request.idempotency_key,
        )
    )
    if existing is not None:
        if existing.actor_user_id != actor_id or not hmac.compare_digest(existing.request_hash, request_hash):
            raise HTTPException(status_code=409, detail="IDEMPOTENCY_KEY_REUSED")
        return ReconcilePurchasedItemsRead.model_validate(existing.response_snapshot).model_copy(
            update={"replayed": True}
        )

    item_ids = [resolution.shopping_item_id for resolution in request.items]
    shopping_items = db.scalars(
        select(ShoppingListItem)
        .where(
            ShoppingListItem.household_id == household_id,
            ShoppingListItem.id.in_(item_ids),
        )
        .order_by(ShoppingListItem.id.asc())
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    by_id = {item.id: item for item in shopping_items}
    for resolution in request.items:
        item = by_id.get(resolution.shopping_item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Shopping item not found")
        if not item.is_bought or item.reconciliation_status != "pending":
            raise HTTPException(status_code=409, detail="SHOPPING_ITEM_NOT_PENDING_REVIEW")
        if item.updated_at != resolution.expected_updated_at:
            raise HTTPException(status_code=409, detail="SHOPPING_ITEM_CHANGED")

    location_ids = {
        resolution.storage_location_id
        for resolution in request.items
        if resolution.action == "add" and resolution.storage_location_id is not None
    }
    if location_ids:
        found_locations = set(
            db.scalars(
                select(StorageLocation.id).where(
                    StorageLocation.household_id == household_id,
                    StorageLocation.id.in_(location_ids),
                )
            ).all()
        )
        if found_locations != location_ids:
            raise HTTPException(status_code=404, detail="Storage location not found")

    products: dict[int, Product] = {}
    requested_barcodes: set[str] = set()
    for resolution in request.items:
        if resolution.action != "add":
            continue
        if resolution.product_id is not None:
            product = db.scalar(
                select(Product).where(
                    Product.id == resolution.product_id,
                    Product.household_id == household_id,
                )
            )
            if product is None:
                raise HTTPException(status_code=404, detail="Product not found")
            if not _same_unit(product.unit, resolution.inventory_unit):
                raise HTTPException(status_code=409, detail="PRODUCT_UNIT_MISMATCH")
            products[resolution.shopping_item_id] = product
            continue

        assert resolution.new_product is not None
        new_product = resolution.new_product
        if not _same_unit(new_product.unit, resolution.inventory_unit):
            raise HTTPException(status_code=422, detail="New product unit must match the entered quantity unit")
        if new_product.barcode:
            if new_product.barcode in requested_barcodes:
                raise HTTPException(status_code=409, detail="DUPLICATE_NEW_PRODUCT_BARCODE")
            requested_barcodes.add(new_product.barcode)
            duplicate_id = db.scalar(
                select(Product.id).where(
                    Product.household_id == household_id,
                    Product.barcode == new_product.barcode,
                )
            )
            if duplicate_id is not None:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "PRODUCT_BARCODE_ALREADY_EXISTS", "product_id": duplicate_id},
                )

    results: list[ReconciledPurchasedItem] = []
    inventory_changed = False
    for resolution in request.items:
        item = by_id[resolution.shopping_item_id]
        if resolution.action == "exclude":
            item.reconciliation_status = "excluded"
            results.append(
                ReconciledPurchasedItem(
                    shopping_item_id=item.id,
                    reconciliation_status="excluded",
                )
            )
            continue

        product = products.get(item.id)
        if product is None:
            assert resolution.new_product is not None
            product = Product(
                household_id=household_id,
                source=ProductSource.USER_CONFIRMED,
                **resolution.new_product.model_dump(mode="python", exclude={"source"}),
            )
            db.add(product)
            db.flush()

        assert resolution.quantity is not None
        purchased_at = db.scalar(select(func.clock_timestamp()))
        batch = InventoryBatch(
            household_id=household_id,
            product_id=product.id,
            storage_location_id=resolution.storage_location_id,
            purchased_at=purchased_at,
            expiration_date=resolution.expiration_date,
            original_quantity=resolution.quantity,
            remaining_quantity=resolution.quantity,
            unit_price=resolution.unit_price,
        )
        db.add(batch)
        db.flush()
        db.add(
            InventoryEvent(
                batch_id=batch.id,
                event_type=EventType.PURCHASED,
                quantity=resolution.quantity,
                occurred_at=purchased_at,
                reason="Shopping list purchase reconciliation",
            )
        )
        item.reconciliation_status = "added_to_pantry"
        inventory_changed = True
        results.append(
            ReconciledPurchasedItem(
                shopping_item_id=item.id,
                reconciliation_status="added_to_pantry",
                product_id=product.id,
                product_name=product.name,
                batch_id=batch.id,
                quantity=resolution.quantity,
                inventory_unit=product.unit,
            )
        )

    response = ReconcilePurchasedItemsRead(items=results)
    db.add(
        ShoppingPantryReconciliationIdempotency(
            household_id=household_id,
            actor_user_id=actor_id,
            idempotency_key=request.idempotency_key,
            request_hash=request_hash,
            response_snapshot=response.model_dump(mode="json"),
        )
    )
    if inventory_changed:
        bump_inventory_revision(db, household_id)
    bump_shopping_revision(db, household_id)
    db.commit()
    return response
