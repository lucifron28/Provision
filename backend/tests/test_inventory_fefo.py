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
        "idempotency_key": "family-dinner-0001",
    }
    res = client.post("/api/v1/inventory/consume", json=consume_payload)
    replay = client.post("/api/v1/inventory/consume", json=consume_payload)
    assert res.status_code == 200
    assert replay.status_code == 200
    assert replay.json() == res.json()
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

    changed_payload = {**consume_payload, "quantity": 1.0}
    conflict = client.post("/api/v1/inventory/consume", json=changed_payload)
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "IDEMPOTENCY_KEY_REUSED"
    assert len(client.get("/api/v1/inventory/events?event_type=CONSUMED").json()) == 2


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


def test_partial_discard_and_adjustment_retries_preserve_distinct_events(client):
    product = client.post("/api/v1/products/", json={"name": "Flour", "unit": "kg"}).json()
    batch = client.post(
        "/api/v1/batches/",
        json={"product_id": product["id"], "original_quantity": "2.50"},
    ).json()

    discard_request = {
        "quantity": "0.75",
        "reason": "Spilled some flour",
        "expected_updated_at": batch["updated_at"],
        "idempotency_key": "flour-discard-0001",
    }
    discard = client.post(f"/api/v1/inventory/batches/{batch['id']}/discard", json=discard_request)
    discard_retry = client.post(f"/api/v1/inventory/batches/{batch['id']}/discard", json=discard_request)
    assert discard.status_code == 200
    assert discard_retry.json() == discard.json()
    assert discard.json()["remaining_quantity"] == 1.75
    discarded_events = client.get(
        f"/api/v1/inventory/events?batch_id={batch['id']}&event_type=DISCARDED"
    ).json()
    assert len(discarded_events) == 1
    assert discarded_events[0]["quantity"] == 0.75

    adjustment_request = {
        "new_remaining_quantity": "1.25",
        "reason": "Checked the bag on the scale",
        "expected_updated_at": discard.json()["updated_at"],
        "idempotency_key": "flour-adjust-0001",
    }
    adjustment = client.post(
        f"/api/v1/inventory/batches/{batch['id']}/adjust", json=adjustment_request
    )
    adjustment_retry = client.post(
        f"/api/v1/inventory/batches/{batch['id']}/adjust", json=adjustment_request
    )
    assert adjustment.status_code == 200
    assert adjustment_retry.json() == adjustment.json()
    assert adjustment.json()["remaining_quantity"] == 1.25
    adjustment_events = client.get(
        f"/api/v1/inventory/events?batch_id={batch['id']}&event_type=ADJUSTMENT"
    ).json()
    assert len(adjustment_events) == 1
    assert adjustment_events[0]["quantity"] == -0.5


def test_stock_actions_reject_stale_batch_updates_and_fractional_count_use(client):
    product = client.post("/api/v1/products/", json={"name": "Eggs", "unit": "pcs"}).json()
    batch = client.post(
        "/api/v1/batches/",
        json={"product_id": product["id"], "original_quantity": 6},
    ).json()
    fractional = client.post(
        "/api/v1/inventory/consume",
        json={"product_id": product["id"], "quantity": "1.50", "idempotency_key": "egg-use-0001"},
    )
    valid_consume = client.post(
        "/api/v1/inventory/consume",
        json={"product_id": product["id"], "quantity": "1.00", "idempotency_key": "egg-use-0002"},
    )
    latest_batch = client.get(f"/api/v1/batches/{batch['id']}").json()
    stale_adjustment = client.post(
        f"/api/v1/inventory/batches/{batch['id']}/adjust",
        json={
            "new_remaining_quantity": 5,
            "reason": "Old count",
            "expected_updated_at": batch["updated_at"],
            "idempotency_key": "egg-adjust-0001",
        },
    )

    assert fractional.status_code == 400
    assert "whole-number" in fractional.json()["detail"]
    assert valid_consume.status_code == 200
    assert stale_adjustment.status_code == 409
    assert stale_adjustment.json()["detail"] == "INVENTORY_BATCH_CHANGED"
    assert latest_batch["remaining_quantity"] == 5.0
    assert len(client.get(f"/api/v1/inventory/events?batch_id={batch['id']}&event_type=ADJUSTMENT").json()) == 0


def test_unrecognized_product_units_are_treated_as_count_based(client):
    product = client.post(
        "/api/v1/products/", json={"name": "Unknown scoop unit", "unit": "scoop"}
    ).json()
    batch = client.post(
        "/api/v1/batches/",
        json={"product_id": product["id"], "original_quantity": 2},
    ).json()

    response = client.post(
        "/api/v1/inventory/consume",
        json={"product_id": product["id"], "quantity": "0.5", "idempotency_key": "unknown-scoop-0001"},
    )

    assert response.status_code == 400
    assert "whole-number" in response.json()["detail"]
    unchanged = client.get(f"/api/v1/batches/{batch['id']}").json()
    assert unchanged["remaining_quantity"] == 2
    assert client.get(
        f"/api/v1/inventory/events?batch_id={batch['id']}&event_type=CONSUMED"
    ).json() == []


def test_stock_action_reasons_cannot_be_blank(client):
    product = client.post(
        "/api/v1/products/", json={"name": "Blank reason test", "unit": "kg"}
    ).json()
    batch = client.post(
        "/api/v1/batches/",
        json={"product_id": product["id"], "original_quantity": 2},
    ).json()

    discard = client.post(
        f"/api/v1/inventory/batches/{batch['id']}/discard",
        json={"quantity": 1, "reason": "   "},
    )
    adjustment = client.post(
        f"/api/v1/inventory/batches/{batch['id']}/adjust",
        json={"new_remaining_quantity": 1, "reason": "   "},
    )

    assert discard.status_code == 422
    assert adjustment.status_code == 422
    assert client.get(f"/api/v1/batches/{batch['id']}").json()["remaining_quantity"] == 2
