from datetime import date, timedelta


def test_fefo_consumption_multi_batch(client):
    # Setup product
    p_res = client.post("/api/v1/products/", json={"name": "Century Tuna", "brand": "Century"})
    product_id = p_res.json()["id"]

    # Batch A: 5 cans, expires in 20 days
    exp_a = (date.today() + timedelta(days=20)).isoformat()
    client.post(
        "/api/v1/batches/",
        json={"product_id": product_id, "original_quantity": 5.0, "expiration_date": exp_a},
    )

    # Batch B: 3 cans, expires in 5 days (earlier expiry)
    exp_b = (date.today() + timedelta(days=5)).isoformat()
    client.post(
        "/api/v1/batches/",
        json={"product_id": product_id, "original_quantity": 3.0, "expiration_date": exp_b},
    )

    # Consume 4 cans
    consume_payload = {
        "product_id": product_id,
        "quantity": 4.0,
        "reason": "Family dinner recipe",
    }
    res = client.post("/api/v1/inventory/consume", json=consume_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["total_consumed"] == 4.0
    assert data["new_total_stock"] == 4.0  # 8 - 4 = 4

    # Check deductions order
    deductions = data["batches_deducted"]
    assert len(deductions) == 2
    # First deduction must be the earlier expiring batch (Batch B, all 3 cans)
    assert deductions[0]["expiration_date"] == exp_b
    assert deductions[0]["quantity_deducted"] == 3.0
    assert deductions[0]["remaining_in_batch"] == 0.0

    # Second deduction must be Batch A (1 can)
    assert deductions[1]["expiration_date"] == exp_a
    assert deductions[1]["quantity_deducted"] == 1.0
    assert deductions[1]["remaining_in_batch"] == 4.0

    # Verify events
    ev_res = client.get("/api/v1/inventory/events?event_type=CONSUMED")
    assert ev_res.status_code == 200
    events = ev_res.json()
    assert len(events) == 2


def test_insufficient_stock_error(client):
    p_res = client.post("/api/v1/products/", json={"name": "Cheddar Cheese"})
    product_id = p_res.json()["id"]

    client.post("/api/v1/batches/", json={"product_id": product_id, "original_quantity": 2.0})

    # Try consuming 5.0
    res = client.post("/api/v1/inventory/consume", json={"product_id": product_id, "quantity": 5.0})
    assert res.status_code == 400
    assert "Insufficient inventory" in res.json()["detail"]


def test_discard_and_adjust_batch(client):
    p_res = client.post("/api/v1/products/", json={"name": "Fresh Spinach"})
    product_id = p_res.json()["id"]

    # Create expired batch
    past_date = (date.today() - timedelta(days=2)).isoformat()
    b_res = client.post(
        "/api/v1/batches/",
        json={"product_id": product_id, "original_quantity": 2.0, "expiration_date": past_date},
    )
    batch_id = b_res.json()["id"]

    # Discard expired batch
    disc_res = client.post(
        f"/api/v1/inventory/batches/{batch_id}/discard",
        json={"reason": "Turned slimy in vegetable crisper"},
    )
    assert disc_res.status_code == 200
    assert disc_res.json()["remaining_quantity"] == 0.0

    # Verify EXPIRED event was logged
    ev_res = client.get(f"/api/v1/inventory/events?batch_id={batch_id}&event_type=EXPIRED")
    assert ev_res.status_code == 200
    assert len(ev_res.json()) == 1

    # Create another batch for adjustment test
    b2_res = client.post(
        "/api/v1/batches/",
        json={"product_id": product_id, "original_quantity": 3.0},
    )
    b2_id = b2_res.json()["id"]

    # Adjust count from 3.0 to 5.0
    adj_res = client.post(
        f"/api/v1/inventory/batches/{b2_id}/adjust",
        json={"new_remaining_quantity": 5.0, "reason": "Found two extra bags"},
    )
    assert adj_res.status_code == 200
    assert adj_res.json()["remaining_quantity"] == 5.0

    # Verify ADJUSTMENT event was logged
    ev_adj = client.get(f"/api/v1/inventory/events?batch_id={b2_id}&event_type=ADJUSTMENT")
    assert ev_adj.status_code == 200
    assert len(ev_adj.json()) == 1
    assert "delta: +2.00" in ev_adj.json()[0]["reason"]
