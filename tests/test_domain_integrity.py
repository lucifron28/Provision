from datetime import date, timedelta
from decimal import Decimal
from app.models.batch import InventoryBatch
from app.models.product import Product


def test_invariants_1_to_5_grocery_session_lifecycle(client):
    """
    1. Draft grocery sessions do not affect inventory.
    2. Cancelled sessions do not affect inventory.
    3. Commit creates batches and PURCHASED events once.
    4. Commit cannot be repeated.
    5. Cancelled session cannot be committed.
    """
    p = client.post("/api/v1/products/", json={"name": "Sourdough Bread"}).json()
    product_id = p["id"]

    # --- Invariant 1: Draft session does not affect inventory ---
    session1 = client.post("/api/v1/grocery-sessions/", json={"store_name": "Bakery"}).json()
    s1_id = session1["id"]
    assert session1["status"] == "DRAFT"

    # Inventory must be 0
    inv1 = client.get(f"/api/v1/batches/?product_id={product_id}").json()
    assert len(inv1) == 0

    # --- Invariant 2: Cancelled session does not affect inventory ---
    cancel_res = client.delete(f"/api/v1/grocery-sessions/{s1_id}")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"

    inv_after_cancel = client.get(f"/api/v1/batches/?product_id={product_id}").json()
    assert len(inv_after_cancel) == 0

    # --- Invariant 5: Cancelled session cannot be committed ---
    commit_cancelled = client.post(
        f"/api/v1/grocery-sessions/{s1_id}/commit",
        json={"items": [{"product_id": product_id, "quantity": 2.0, "unit_price": 120.0}]},
    )
    assert commit_cancelled.status_code == 400
    assert "cancelled" in commit_cancelled.json()["detail"].lower()

    # --- Invariant 3: Commit creates batches and PURCHASED events once ---
    session2 = client.post("/api/v1/grocery-sessions/", json={"store_name": "Supermarket"}).json()
    s2_id = session2["id"]

    commit_res = client.post(
        f"/api/v1/grocery-sessions/{s2_id}/commit",
        json={
            "items": [
                {
                    "product_id": product_id,
                    "quantity": 3.0,
                    "unit_price": 115.50,
                    "expiration_date": (date.today() + timedelta(days=5)).isoformat(),
                }
            ],
            "total_amount": 346.50,
        },
    )
    assert commit_res.status_code == 200
    committed = commit_res.json()
    assert committed["status"] == "COMPLETED"
    assert len(committed["batches"]) == 1
    batch_id = committed["batches"][0]["id"]

    # Verify batch in inventory
    batches = client.get(f"/api/v1/batches/?product_id={product_id}").json()
    assert len(batches) == 1
    assert batches[0]["remaining_quantity"] == 3.0
    assert Decimal(str(batches[0]["unit_price"])) == Decimal("115.50")

    # Verify PURCHASED event was logged exactly once
    events = client.get(f"/api/v1/inventory/events?batch_id={batch_id}").json()
    assert len(events) == 1
    assert events[0]["event_type"] == "PURCHASED"
    assert events[0]["quantity"] == 3.0

    # --- Invariant 4: Commit cannot be repeated ---
    recommit_res = client.post(
        f"/api/v1/grocery-sessions/{s2_id}/commit",
        json={"items": [{"product_id": product_id, "quantity": 1.0}]},
    )
    assert recommit_res.status_code == 400
    assert "already completed" in recommit_res.json()["detail"].lower()


def test_invariant_6_batch_patch_cannot_change_remaining_quantity(client):
    """
    6. Batch PATCH cannot change remaining quantity.
    """
    p = client.post("/api/v1/products/", json={"name": "Olive Oil"}).json()
    b = client.post(
        "/api/v1/batches/",
        json={"product_id": p["id"], "original_quantity": 4.0, "unit_price": 250.0},
    ).json()
    batch_id = b["id"]

    # Attempt to directly modify remaining_quantity via PATCH
    res = client.patch(
        f"/api/v1/batches/{batch_id}",
        json={"remaining_quantity": 1.0, "unit_price": 260.0},
    )
    assert res.status_code == 200
    data = res.json()
    # unit_price should update, but remaining_quantity MUST remain untouched
    assert Decimal(str(data["unit_price"])) == Decimal("260.00")
    assert data["remaining_quantity"] == 4.0

    # Verify in database
    get_res = client.get(f"/api/v1/batches/{batch_id}").json()
    assert get_res["remaining_quantity"] == 4.0


def test_invariants_7_and_8_deletion_protection(client, db):
    """
    7. Product deletion cannot destroy inventory history (409 Conflict).
    8. Batch deletion cannot destroy inventory events (409 Conflict).
    - An empty/new product may be deleted.
    - A batch with no events may be deleted if such a state exists.
    """
    # Create product and batch with event
    p1 = client.post("/api/v1/products/", json={"name": "Tuna Can"}).json()
    b1 = client.post(
        "/api/v1/batches/",
        json={"product_id": p1["id"], "original_quantity": 2.0},
    ).json()

    # Invariant 7: Product with batches cannot be deleted
    del_prod_res = client.delete(f"/api/v1/products/{p1['id']}")
    assert del_prod_res.status_code == 409
    assert "associated inventory batch" in del_prod_res.json()["detail"].lower()

    # Invariant 8: Batch with events cannot be deleted
    del_batch_res = client.delete(f"/api/v1/batches/{b1['id']}")
    assert del_batch_res.status_code == 409
    assert "associated inventory event" in del_batch_res.json()["detail"].lower()

    # Empty product without batches can be deleted
    p2 = client.post("/api/v1/products/", json={"name": "Empty Product"}).json()
    del_empty_p = client.delete(f"/api/v1/products/{p2['id']}")
    assert del_empty_p.status_code == 204

    # Batch with no events can be deleted
    # Manually insert batch into DB with no events
    orphan_batch = InventoryBatch(
        product_id=p1["id"],
        original_quantity=1.0,
        remaining_quantity=1.0,
    )
    db.add(orphan_batch)
    db.commit()
    db.refresh(orphan_batch)

    del_orphan = client.delete(f"/api/v1/batches/{orphan_batch.id}")
    assert del_orphan.status_code == 204


def test_invariant_9_session_patch_cannot_change_status(client):
    """
    9. Session PATCH cannot change status, and invalid transitions are rejected.
    """
    session = client.post("/api/v1/grocery-sessions/", json={"store_name": "Costco"}).json()
    s_id = session["id"]

    # Try to sneakily change status from DRAFT to COMPLETED via PATCH
    patch_res = client.patch(f"/api/v1/grocery-sessions/{s_id}", json={"status": "COMPLETED"})
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "DRAFT"

    # Try to change status from DRAFT to CANCELLED via PATCH
    patch_res2 = client.patch(f"/api/v1/grocery-sessions/{s_id}", json={"status": "CANCELLED"})
    assert patch_res2.status_code == 200
    assert patch_res2.json()["status"] == "DRAFT"

    # Commit legitimately
    client.post(f"/api/v1/grocery-sessions/{s_id}/commit", json={})

    # Cannot patch an already completed session
    patch_completed = client.patch(f"/api/v1/grocery-sessions/{s_id}", json={"notes": "Updated"})
    assert patch_completed.status_code == 400
    assert "cannot edit session" in patch_completed.json()["detail"].lower()


def test_invariants_10_and_11_signed_adjustments(client):
    """
    10. Positive adjustment creates positive delta.
    11. Negative adjustment creates negative delta.
    """
    p = client.post("/api/v1/products/", json={"name": "Apples"}).json()
    b = client.post(
        "/api/v1/batches/",
        json={"product_id": p["id"], "original_quantity": 5.0},
    ).json()
    batch_id = b["id"]

    # Negative adjustment: 5.0 -> 3.0 (delta = -2.0)
    adj_neg = client.post(
        f"/api/v1/inventory/batches/{batch_id}/adjust",
        json={"new_remaining_quantity": 3.0, "reason": "Count discrepancy (missing)"},
    )
    assert adj_neg.status_code == 200
    assert adj_neg.json()["remaining_quantity"] == 3.0

    # Verify event has negative quantity -2.0
    ev_neg = client.get(f"/api/v1/inventory/events?batch_id={batch_id}&event_type=ADJUSTMENT").json()
    assert len(ev_neg) == 1
    assert ev_neg[0]["quantity"] == -2.0

    # Positive adjustment: 3.0 -> 7.0 (delta = +4.0)
    adj_pos = client.post(
        f"/api/v1/inventory/batches/{batch_id}/adjust",
        json={"new_remaining_quantity": 7.0, "reason": "Found more in back"},
    )
    assert adj_pos.status_code == 200
    assert adj_pos.json()["remaining_quantity"] == 7.0

    # Verify event has positive quantity +4.0
    ev_all = client.get(f"/api/v1/inventory/events?batch_id={batch_id}&event_type=ADJUSTMENT").json()
    assert len(ev_all) == 2
    # Newest event first
    assert ev_all[0]["quantity"] == 4.0
    assert ev_all[1]["quantity"] == -2.0


def test_invariant_12_decimal_monetary_calculations(client):
    """
    12. Monetary calculations use Decimal-compatible behavior without float precision loss.
    """
    p = client.post("/api/v1/products/", json={"name": "Fine Coffee"}).json()

    # Ingest 3 batches with specific precision numbers:
    # 3.0 @ 49.99 = 149.97
    # 2.0 @ 19.99 = 39.98
    # Total valuation = 189.95
    client.post(
        "/api/v1/batches/",
        json={"product_id": p["id"], "original_quantity": 3.0, "unit_price": 49.99},
    )
    client.post(
        "/api/v1/batches/",
        json={"product_id": p["id"], "original_quantity": 2.0, "unit_price": 19.99},
    )

    val_res = client.get("/api/v1/analytics/valuation")
    assert val_res.status_code == 200
    val_data = val_res.json()
    assert Decimal(str(val_data["total_value"])) == Decimal("189.95")

    # Test grocery session total computation via Decimal
    session = client.post("/api/v1/grocery-sessions/", json={"store_name": "Coffee Roasters"}).json()
    commit_res = client.post(
        f"/api/v1/grocery-sessions/{session['id']}/commit",
        json={
            "items": [
                {"product_id": p["id"], "quantity": 1.0, "unit_price": 33.33},
                {"product_id": p["id"], "quantity": 2.0, "unit_price": 11.11},
            ]
        },
    )
    assert commit_res.status_code == 200
    committed = commit_res.json()
    # 33.33 + 22.22 = 55.55
    assert Decimal(str(committed["total_amount"])) == Decimal("55.55")

    # Spending summary uses Decimal
    spending_res = client.get("/api/v1/analytics/spending")
    assert spending_res.status_code == 200
    spending_data = spending_res.json()
    assert Decimal(str(spending_data["total_spent"])) == Decimal("55.55")
