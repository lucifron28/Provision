import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

def test_manual_inventory_lifecycle(client: TestClient, db: Session):
    # 1. Create product (omitted source defaults to USER_CONFIRMED)
    prod_res = client.post("/api/v1/products/", json={
        "name": "Milk",
        "unit": "bottles"
    })
    assert prod_res.status_code == 201
    prod_data = prod_res.json()
    assert prod_data["source"] == "USER_CONFIRMED"
    prod_id = prod_data["id"]

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

    # --- Scenario: update and clear expiration date ---
    upd_res = client.patch(f"/api/v1/batches/{b2_id}", json={
        "expiration_date": tomorrow
    })
    assert upd_res.status_code == 200
    assert upd_res.json()["expiration_date"] == tomorrow

    # Clear expiration date -> null
    upd2_res = client.patch(f"/api/v1/batches/{b2_id}", json={
        "expiration_date": None
    })
    assert upd2_res.status_code == 200
    assert upd2_res.json()["expiration_date"] is None

    # --- Scenario: update and clear storage location ---
    loc_res = client.post("/api/v1/locations/", json={"name": "Fridge"})
    loc_id = loc_res.json()["id"]
    
    upd3_res = client.patch(f"/api/v1/batches/{b2_id}", json={
        "storage_location_id": loc_id
    })
    assert upd3_res.status_code == 200
    assert upd3_res.json()["storage_location"]["name"] == "Fridge"

    # Clear storage_location_id -> null
    clear_loc_res = client.patch(f"/api/v1/batches/{b2_id}", json={
        "storage_location_id": None
    })
    assert clear_loc_res.status_code == 200
    assert clear_loc_res.json()["storage_location_id"] is None
    assert clear_loc_res.json()["storage_location"] is None

    # --- Scenario: update and clear unit price ---
    upd_price_res = client.patch(f"/api/v1/batches/{b2_id}", json={
        "unit_price": "45.50"
    })
    assert upd_price_res.status_code == 200
    assert float(upd_price_res.json()["unit_price"]) == 45.50

    # Clear unit_price -> null
    clear_price_res = client.patch(f"/api/v1/batches/{b2_id}", json={
        "unit_price": None
    })
    assert clear_price_res.status_code == 200
    assert clear_price_res.json()["unit_price"] is None

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


def test_decimal_quantity_lifecycle(client: TestClient):
    # PATCH 11: Create batch with original_quantity = 2.5, consume 0.5, expect remaining_quantity = 2.0
    prod_res = client.post("/api/v1/products/", json={
        "name": "Rice",
        "unit": "kg"
    })
    assert prod_res.status_code == 201
    prod_data = prod_res.json()
    assert prod_data["source"] == "USER_CONFIRMED"
    prod_id = prod_data["id"]

    batch_res = client.post("/api/v1/batches/", json={
        "product_id": prod_id,
        "original_quantity": 2.5
    })
    assert batch_res.status_code == 201
    batch_id = batch_res.json()["id"]
    assert batch_res.json()["remaining_quantity"] == 2.5

    con_res = client.post("/api/v1/inventory/consume", json={
        "product_id": prod_id,
        "quantity": 0.5,
        "reason": "Cooked dinner"
    })
    assert con_res.status_code == 200
    assert con_res.json()["total_consumed"] == 0.5

    b_check = client.get(f"/api/v1/batches/{batch_id}")
    assert b_check.status_code == 200
    assert b_check.json()["remaining_quantity"] == 2.0


def test_stock_amount_semantics(client: TestClient):
    # Amount 5 -> original_quantity 5.0, unit kg
    prod_res = client.post("/api/v1/products/", json={
        "name": "Jasmine Rice",
        "unit": "kg"
    })
    assert prod_res.status_code == 201
    prod_id = prod_res.json()["id"]
    assert prod_res.json()["unit"] == "kg"

    # Batch A: 5 kg
    b1_res = client.post("/api/v1/batches/", json={
        "product_id": prod_id,
        "original_quantity": 5.0
    })
    assert b1_res.status_code == 201
    assert b1_res.json()["original_quantity"] == 5.0
    assert b1_res.json()["remaining_quantity"] == 5.0

    p_check = client.get(f"/api/v1/products/{prod_id}")
    assert p_check.json()["total_remaining_quantity"] == 5.0

    # Restock Batch B: 2.5 kg
    b2_res = client.post("/api/v1/batches/", json={
        "product_id": prod_id,
        "original_quantity": 2.5
    })
    assert b2_res.status_code == 201
    assert b2_res.json()["original_quantity"] == 2.5

    p_check2 = client.get(f"/api/v1/products/{prod_id}")
    assert p_check2.json()["total_remaining_quantity"] == 7.5
    assert p_check2.json()["active_batches_count"] == 2

    # Consume 0.75 kg
    con_res = client.post("/api/v1/inventory/consume", json={
        "product_id": prod_id,
        "quantity": 0.75,
        "reason": "Lunch"
    })
    assert con_res.status_code == 200
    assert con_res.json()["total_consumed"] == 0.75

    p_check3 = client.get(f"/api/v1/products/{prod_id}")
    assert p_check3.json()["total_remaining_quantity"] == 6.75

