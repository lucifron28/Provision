from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.batch import InventoryBatch
from app.models.event import InventoryEvent
from app.models.household import Household
from app.models.location import StorageLocation
from app.models.product import Product


def _payload(**overrides):
    payload = {
        "idempotency_key": "manual-intake-0001",
        "new_product": {"name": "Jasmine rice", "unit": "kg"},
        "quantity": "2.5",
        "unit_price": "42.00",
    }
    payload.update(overrides)
    return payload


def test_new_product_and_initial_batch_are_created_atomically_without_location(
    client: TestClient, db: Session
):
    response = client.post("/api/v1/inventory/manual-intake", json=_payload())

    assert response.status_code == 201
    result = response.json()
    product = db.get(Product, result["product_id"])
    batch = db.get(InventoryBatch, result["batch_id"])
    assert product.name == "Jasmine rice"
    assert batch.product_id == product.id
    assert batch.storage_location_id is None
    assert batch.original_quantity == Decimal("2.50")
    assert batch.remaining_quantity == Decimal("2.50")
    assert db.scalar(select(func.count(InventoryEvent.id)).where(InventoryEvent.batch_id == batch.id)) == 1


def test_manual_intake_exact_retry_replays_without_duplicate_writes(client: TestClient, db: Session):
    payload = _payload()
    first = client.post("/api/v1/inventory/manual-intake", json=payload)
    retry = client.post("/api/v1/inventory/manual-intake", json=payload)

    assert first.status_code == 201
    assert retry.status_code == 200
    assert retry.json()["replayed"] is True
    assert retry.json()["product_id"] == first.json()["product_id"]
    assert retry.json()["batch_id"] == first.json()["batch_id"]
    assert db.scalar(select(func.count(Product.id))) == 1
    assert db.scalar(select(func.count(InventoryBatch.id))) == 1
    assert db.scalar(select(func.count(InventoryEvent.id))) == 1


def test_manual_intake_rejects_reused_key_with_changed_payload(client: TestClient, db: Session):
    first = client.post("/api/v1/inventory/manual-intake", json=_payload())
    changed = _payload(quantity="3.0")

    assert first.status_code == 201
    response = client.post("/api/v1/inventory/manual-intake", json=changed)

    assert response.status_code == 409
    assert response.json()["detail"] == "IDEMPOTENCY_KEY_REUSED"
    assert db.scalar(select(func.count(Product.id))) == 1
    assert db.scalar(select(func.count(InventoryBatch.id))) == 1


def test_manual_intake_adds_to_an_existing_household_product(client: TestClient, db: Session, auth_household):
    product = Product(household_id=auth_household.id, name="Canned tomatoes", unit="cans")
    db.add(product)
    db.commit()
    db.refresh(product)

    response = client.post(
        "/api/v1/inventory/manual-intake",
        json=_payload(
            idempotency_key="manual-intake-existing-1",
            new_product=None,
            product_id=product.id,
        ),
    )

    assert response.status_code == 201
    assert response.json()["product_id"] == product.id
    assert db.scalar(select(func.count(Product.id))) == 1
    assert db.scalar(select(func.count(InventoryBatch.id))) == 1


def test_manual_intake_rejects_foreign_household_product_and_location(
    client: TestClient, db: Session, auth_household
):
    other_household = Household(name="Other Home", slug="other-manual-intake-home")
    db.add(other_household)
    db.flush()
    foreign_product = Product(household_id=other_household.id, name="Private product", unit="pcs")
    foreign_location = StorageLocation(household_id=other_household.id, name="Private pantry")
    db.add_all([foreign_product, foreign_location])
    db.commit()
    db.refresh(foreign_product)
    db.refresh(foreign_location)

    product_response = client.post(
        "/api/v1/inventory/manual-intake",
        json=_payload(idempotency_key="manual-intake-foreign-prod", new_product=None,
                      product_id=foreign_product.id),
    )
    location_response = client.post(
        "/api/v1/inventory/manual-intake",
        json=_payload(idempotency_key="manual-intake-foreign-loc",
                      storage_location_id=foreign_location.id),
    )

    assert product_response.status_code == 404
    assert location_response.status_code == 404
    assert db.scalar(select(func.count(Product.id)).where(Product.household_id == auth_household.id)) == 0
    assert db.scalar(select(func.count(InventoryBatch.id))) == 0


def test_manual_intake_rejects_duplicate_barcode_without_partial_records(
    client: TestClient, db: Session, auth_household
):
    db.add(Product(household_id=auth_household.id, name="Existing rice", barcode="12345678", unit="kg"))
    db.commit()

    response = client.post(
        "/api/v1/inventory/manual-intake",
        json=_payload(new_product={"name": "Duplicate rice", "barcode": "12345678", "unit": "kg"}),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PRODUCT_BARCODE_ALREADY_EXISTS"
    assert db.scalar(select(func.count(Product.id)).where(Product.household_id == auth_household.id)) == 1
    assert db.scalar(select(func.count(InventoryBatch.id))) == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"product_id": 1, "new_product": {"name": "Both", "unit": "pcs"}},
        {"product_id": None, "new_product": None},
    ],
)
def test_manual_intake_requires_exactly_one_product_source(client: TestClient, payload):
    response = client.post(
        "/api/v1/inventory/manual-intake",
        json=_payload(**payload),
    )

    assert response.status_code == 422
