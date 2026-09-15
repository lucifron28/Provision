import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

def test_manual_inventory_lifecycle(client: TestClient, db: Session):
    # 1. Create product
    prod_res = client.post("/api/v1/products/", json={
        "name": "Milk",
        "unit": "bottles"
    })
    assert prod_res.status_code == 201
    prod_id = prod_res.json()["id"]

    # --- Scenario: Batch creation with expiration ---
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    b1_res = client.post("/api/v1/batches/", json={
        "product_id": prod_id,
        "original_quantity": 2.0,
        "expiration_date": tomorrow
    })
    assert b1_res.status_code == 201
    b1_id = b1_res.json()["id"]

    # --- Scenario: Batch creation without expiration ---
    b2_res = client.post("/api/v1/batches/", json={
        "product_id": prod_id,
        "original_quantity": 3.0
    })
    assert b2_res.status_code == 201
    b2_id = b2_res.json()["id"]

    # --- Expiring Soon (Initial Check) ---
    exp_res = client.get("/api/v1/analytics/expiring-soon")
    assert exp_res.status_code == 200
    exp_items = exp_res.json()
    batch_ids = [item["batch_id"] for item in exp_items]
    assert b1_id in batch_ids # Tomorrow is expiring soon

    # --- Scenario: FEFO fully consumed batch reaches zero ---
    con_res = client.post("/api/v1/inventory/consume", json={
        "product_id": prod_id,
        "quantity": 2.0,
        "reason": "Used"
    })
    assert con_res.status_code == 200

    b1_check = client.get(f"/api/v1/batches/{b1_id}")
    assert b1_check.json()["remaining_quantity"] == 0.0

    # --- Scenario: fully consumed batch disappears from active batch query ---
    active_res = client.get(f"/api/v1/batches/?product_id={prod_id}&active_only=true")
    active_ids = [b["id"] for b in active_res.json()]
    assert b1_id not in active_ids
    assert b2_id in active_ids

    # --- Scenario: batch with zero remaining quantity is excluded from expiring-soon ---
    exp_res2 = client.get("/api/v1/analytics/expiring-soon")
    batch_ids2 = [item["batch_id"] for item in exp_res2.json()]
    assert b1_id not in batch_ids2

    # --- Scenario: update expiration date ---
    upd_res = client.patch(f"/api/v1/batches/{b2_id}", json={
        "expiration_date": tomorrow
    })
    assert upd_res.status_code == 200
    assert upd_res.json()["expiration_date"] == tomorrow

    # --- Scenario: clear expiration date if supported ---
    upd2_res = client.patch(f"/api/v1/batches/{b2_id}", json={
        "expiration_date": None
    })
    assert upd2_res.status_code == 200
    assert upd2_res.json()["expiration_date"] is None

    # --- Scenario: update storage location ---
    loc_res = client.post("/api/v1/locations/", json={"name": "Fridge"})
    loc_id = loc_res.json()["id"]
    
    upd3_res = client.patch(f"/api/v1/batches/{b2_id}", json={
        "storage_location_id": loc_id
    })
    assert upd3_res.status_code == 200
    assert upd3_res.json()["storage_location"]["name"] == "Fridge"

    # --- Scenario: quantity adjustment still creates event ---
    adj_res = client.post(f"/api/v1/inventory/batches/{b2_id}/adjust", json={
        "new_remaining_quantity": 5.0,
        "reason": "Found more"
    })
    assert adj_res.status_code == 200
    assert adj_res.json()["remaining_quantity"] == 5.0
    
    ev_res = client.get(f"/api/v1/inventory/events?batch_id={b2_id}")
    assert any(e["event_type"] == "ADJUSTMENT" for e in ev_res.json())

    # --- Scenario: expired batch with remaining quantity IS returned ---
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    b3_res = client.post("/api/v1/batches/", json={
        "product_id": prod_id,
        "original_quantity": 1.0,
        "expiration_date": yesterday
    })
    assert b3_res.status_code == 201
    b3_id = b3_res.json()["id"]

    exp_res3 = client.get("/api/v1/analytics/expiring-soon")
    batch_ids3 = [item["batch_id"] for item in exp_res3.json()]
    assert b3_id in batch_ids3

    # --- Scenario: expired batch with zero remaining quantity is NOT returned ---
    client.post("/api/v1/inventory/consume", json={
        "product_id": prod_id,
        "quantity": 1.0,
        "reason": "Test"
    })
    b3_check = client.get(f"/api/v1/batches/{b3_id}")
    assert b3_check.json()["remaining_quantity"] == 0.0

    exp_res4 = client.get("/api/v1/analytics/expiring-soon")
    batch_ids4 = [item["batch_id"] for item in exp_res4.json()]
    assert b3_id not in batch_ids4
