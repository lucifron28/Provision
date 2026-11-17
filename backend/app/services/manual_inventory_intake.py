import hashlib
import hmac
import json

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.batch import InventoryBatch
from app.models.event import EventType, InventoryEvent
from app.models.location import StorageLocation
from app.models.manual_inventory_intake import ManualInventoryIntakeIdempotency
from app.models.product import Product
from app.schemas.manual_inventory_intake import (
    ManualInventoryIntakeRead,
    ManualInventoryIntakeRequest,
)
from app.services.household_writes import bump_inventory_revision, lock_household_write


def _request_hash(request: ManualInventoryIntakeRequest) -> str:
    body = request.model_dump(mode="json", exclude={"idempotency_key"})
    encoded = json.dumps(body, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def create_manual_inventory_intake(
    db: Session,
    household_id: int,
    actor_id: int,
    request: ManualInventoryIntakeRequest,
) -> ManualInventoryIntakeRead:
    lock_household_write(db, household_id, actor_id=actor_id)
    request_hash = _request_hash(request)
    existing = db.scalar(
        select(ManualInventoryIntakeIdempotency).where(
            ManualInventoryIntakeIdempotency.household_id == household_id,
            ManualInventoryIntakeIdempotency.idempotency_key == request.idempotency_key,
        )
    )
    if existing is not None:
        if existing.actor_user_id != actor_id or not hmac.compare_digest(
            existing.request_hash, request_hash
        ):
            raise HTTPException(status_code=409, detail="IDEMPOTENCY_KEY_REUSED")
        return ManualInventoryIntakeRead.model_validate(existing.response_snapshot).model_copy(
            update={"replayed": True}
        )

    if request.storage_location_id is not None:
        location_exists = db.scalar(
            select(StorageLocation.id).where(
                StorageLocation.id == request.storage_location_id,
                StorageLocation.household_id == household_id,
            )
        )
        if location_exists is None:
            raise HTTPException(status_code=404, detail="Storage location not found")

    if request.product_id is not None:
        product = db.scalar(
            select(Product).where(
                Product.id == request.product_id,
                Product.household_id == household_id,
            )
        )
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")
    else:
        assert request.new_product is not None
        if request.new_product.barcode:
            duplicate = db.scalar(
                select(Product.id).where(
                    Product.household_id == household_id,
                    Product.barcode == request.new_product.barcode,
                )
            )
            if duplicate is not None:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "PRODUCT_BARCODE_ALREADY_EXISTS", "product_id": duplicate},
                )
        product = Product(
            household_id=household_id,
            **request.new_product.model_dump(mode="python"),
        )
        db.add(product)
        db.flush()

    purchased_at = request.purchased_at or db.scalar(select(func.clock_timestamp()))
    batch = InventoryBatch(
        household_id=household_id,
        product_id=product.id,
        storage_location_id=request.storage_location_id,
        purchased_at=purchased_at,
        expiration_date=request.expiration_date,
        original_quantity=request.quantity,
        remaining_quantity=request.quantity,
        unit_price=request.unit_price,
    )
    db.add(batch)
    db.flush()
    event = InventoryEvent(
        batch_id=batch.id,
        event_type=EventType.PURCHASED,
        quantity=request.quantity,
        occurred_at=purchased_at,
        reason="Manual inventory intake",
    )
    db.add(event)
    response = ManualInventoryIntakeRead(
        product_id=product.id,
        product_name=product.name,
        unit=product.unit,
        batch_id=batch.id,
        quantity=float(request.quantity),
        expiration_date=request.expiration_date,
        storage_location_id=request.storage_location_id,
    )
    db.add(
        ManualInventoryIntakeIdempotency(
            household_id=household_id,
            actor_user_id=actor_id,
            idempotency_key=request.idempotency_key,
            request_hash=request_hash,
            response_snapshot=response.model_dump(mode="json"),
        )
    )
    bump_inventory_revision(db, household_id)
    db.commit()
    return response
