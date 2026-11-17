from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.batch import InventoryBatch
from app.models.event import InventoryEvent
from app.models.household import Household
from app.models.product import Product
from app.models.shopping import ShoppingListItem


def _purchased_item(client, name: str) -> tuple[dict, dict]:
    created = client.post("/api/v1/shopping-list/", json={"name": name, "quantity": 2, "unit": "packs"})
    assert created.status_code == 201
    toggled = client.post(f"/api/v1/shopping-list/{created.json()['id']}/toggle")
    assert toggled.status_code == 200
    return created.json(), toggled.json()


def _resolution(shopping_item: dict, **overrides) -> dict:
    payload = {
        "shopping_item_id": shopping_item["id"],
        "expected_updated_at": shopping_item["updated_at"],
        "action": "exclude",
    }
    payload.update(overrides)
    return payload


def test_reconcile_add_exclude_and_exact_retry_are_atomic(client, db: Session, auth_household):
    _, existing_item = _purchased_item(client, "Olive oil")
    _, new_item = _purchased_item(client, "Coconut milk")
    _, excluded_item = _purchased_item(client, "Duplicate tomatoes")
    product_response = client.post(
        "/api/v1/products/", json={"name": "Olive oil", "unit": "bottles"}
    )
    assert product_response.status_code == 201
    product_id = product_response.json()["id"]
    payload = {
        "idempotency_key": "grocery-trip-0001",
        "items": [
            _resolution(
                existing_item,
                action="add",
                product_id=product_id,
                quantity="1.00",
                inventory_unit="bottles",
                unit_price="8.50",
            ),
            _resolution(
                new_item,
                action="add",
                new_product={"name": "Coconut milk", "unit": "cans"},
                quantity="3.00",
                inventory_unit="cans",
            ),
            _resolution(excluded_item),
        ],
    }

    first = client.post("/api/v1/shopping-list/reconcile-purchased", json=payload)
    retry = client.post("/api/v1/shopping-list/reconcile-purchased", json=payload)

    assert first.status_code == 201
    assert retry.status_code == 200
    assert retry.json()["replayed"] is True
    results = first.json()["items"]
    assert [row["reconciliation_status"] for row in results] == [
        "added_to_pantry",
        "added_to_pantry",
        "excluded",
    ]
    assert db.scalar(select(func.count(InventoryBatch.id))) == 2
    assert db.scalar(select(func.count(InventoryEvent.id))) == 2
    assert db.scalar(select(func.count(Product.id))) == 2
    assert db.scalar(
        select(func.count(ShoppingListItem.id)).where(
            ShoppingListItem.reconciliation_status == "added_to_pantry"
        )
    ) == 2
    assert db.scalar(
        select(func.count(ShoppingListItem.id)).where(ShoppingListItem.reconciliation_status == "excluded")
    ) == 1
    batches = db.scalars(select(InventoryBatch).order_by(InventoryBatch.id)).all()
    assert [batch.original_quantity for batch in batches] == [Decimal("1.00"), Decimal("3.00")]

    changed_payload = {**payload, "items": [dict(payload["items"][0], quantity="2.00"), *payload["items"][1:]]}
    conflict = client.post("/api/v1/shopping-list/reconcile-purchased", json=changed_payload)
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "IDEMPOTENCY_KEY_REUSED"
    assert db.scalar(select(func.count(InventoryBatch.id))) == 2


def test_reconcile_rejects_stale_rows_and_unit_mismatch_without_writes(client, db: Session):
    created, bought = _purchased_item(client, "Rice")
    product = client.post("/api/v1/products/", json={"name": "Rice", "unit": "kg"}).json()
    stale = client.post(
        "/api/v1/shopping-list/reconcile-purchased",
        json={
            "idempotency_key": "stale-grocery-001",
            "items": [
                _resolution(
                    {**bought, "updated_at": created["updated_at"]},
                    action="add",
                    product_id=product["id"],
                    quantity="1.00",
                    inventory_unit="kg",
                )
            ],
        },
    )
    mismatch = client.post(
        "/api/v1/shopping-list/reconcile-purchased",
        json={
            "idempotency_key": "unit-grocery-001",
            "items": [
                _resolution(
                    bought,
                    action="add",
                    product_id=product["id"],
                    quantity="1.00",
                    inventory_unit="g",
                )
            ],
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"] == "SHOPPING_ITEM_CHANGED"
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"] == "PRODUCT_UNIT_MISMATCH"
    assert db.scalar(select(func.count(InventoryBatch.id))) == 0


def test_reconcile_rejects_duplicate_new_product_barcodes_before_writes(client, db: Session):
    _, rice = _purchased_item(client, "Rice")
    _, oats = _purchased_item(client, "Oats")

    def resolution(item: dict) -> dict:
        return _resolution(
            item,
            action="add",
            new_product={"name": item["name"], "barcode": "123456789012", "unit": "packs"},
            quantity="1.00",
            inventory_unit="packs",
        )

    response = client.post(
        "/api/v1/shopping-list/reconcile-purchased",
        json={
            "idempotency_key": "duplicate-barcode-001",
            "items": [resolution(rice), resolution(oats)],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "DUPLICATE_NEW_PRODUCT_BARCODE"
    assert db.scalar(select(func.count(InventoryBatch.id))) == 0
    assert db.scalar(select(func.count(Product.id))) == 0


def test_reconcile_validates_every_row_before_writing_and_is_household_scoped(
    client, db: Session, auth_household
):
    _, first = _purchased_item(client, "Flour")
    _, second = _purchased_item(client, "Sugar")
    valid_product = client.post("/api/v1/products/", json={"name": "Flour", "unit": "kg"}).json()
    invalid_product = client.post("/api/v1/products/", json={"name": "Sugar", "unit": "kg"}).json()
    other = Household(name="Another home", slug="another-reconciliation-home")
    db.add(other)
    db.flush()
    foreign_item = ShoppingListItem(
        household_id=other.id,
        name="Private rice",
        quantity=Decimal("1"),
        unit="kg",
        is_bought=True,
    )
    foreign_product = Product(household_id=other.id, name="Private rice", unit="kg")
    db.add_all([foreign_item, foreign_product])
    db.commit()
    db.refresh(foreign_item)
    db.refresh(foreign_product)

    partial = client.post(
        "/api/v1/shopping-list/reconcile-purchased",
        json={
            "idempotency_key": "atomic-grocery-001",
            "items": [
                _resolution(
                    first,
                    action="add",
                    product_id=valid_product["id"],
                    quantity="1.00",
                    inventory_unit="kg",
                ),
                _resolution(
                    second,
                    action="add",
                    product_id=invalid_product["id"],
                    quantity="1.00",
                    inventory_unit="g",
                ),
            ],
        },
    )
    foreign = client.post(
        "/api/v1/shopping-list/reconcile-purchased",
        json={
            "idempotency_key": "foreign-grocery-001",
            "items": [
                {
                    "shopping_item_id": foreign_item.id,
                    "expected_updated_at": foreign_item.updated_at.isoformat(),
                    "action": "exclude",
                }
            ],
        },
    )
    foreign_product_response = client.post(
        "/api/v1/shopping-list/reconcile-purchased",
        json={
            "idempotency_key": "foreign-prod-groc-001",
            "items": [
                _resolution(
                    first,
                    action="add",
                    product_id=foreign_product.id,
                    quantity="1.00",
                    inventory_unit="kg",
                )
            ],
        },
    )

    assert partial.status_code == 409
    assert partial.json()["detail"] == "PRODUCT_UNIT_MISMATCH"
    assert foreign.status_code == 404
    assert foreign_product_response.status_code == 404
    assert db.scalar(select(func.count(InventoryBatch.id))) == 0
    assert db.scalar(select(func.count(Product.id)).where(Product.household_id == auth_household.id)) == 2


def test_pending_purchases_cannot_be_deleted_and_clear_preserves_them(client):
    _, pending_one = _purchased_item(client, "Apples")
    _, pending_two = _purchased_item(client, "Bananas")
    _, processed = _purchased_item(client, "Wrong item")
    excluded = client.post(
        "/api/v1/shopping-list/reconcile-purchased",
        json={
            "idempotency_key": "exclude-grocery-001",
            "items": [_resolution(processed)],
        },
    )
    assert excluded.status_code == 201

    delete_pending = client.delete(f"/api/v1/shopping-list/{pending_one['id']}")
    assert delete_pending.status_code == 409
    clear = client.delete("/api/v1/shopping-list/completed/clear")

    assert clear.status_code == 200
    assert clear.json()["removed_count"] == 1
    assert clear.json()["pending_review_count"] == 2
    assert client.get(f"/api/v1/shopping-list/{pending_one['id']}").status_code == 200
    assert client.get(f"/api/v1/shopping-list/{pending_two['id']}").status_code == 200
