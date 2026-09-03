from datetime import date, timedelta


def test_grocery_session_full_flow(client):
    # Setup products and location
    p1 = client.post("/api/v1/products/", json={"name": "Almond Milk", "brand": "Silk"}).json()
    p2 = client.post("/api/v1/products/", json={"name": "Whole Wheat Bread", "brand": "Gardenia"}).json()
    loc = client.post("/api/v1/locations/", json={"name": "Kitchen Counter"}).json()

    # 1. Start Session
    session_res = client.post(
        "/api/v1/grocery-sessions/",
        json={"store_name": "SM Supermarket", "notes": "Weekly grocery intake"},
    )
    assert session_res.status_code == 201
    session = session_res.json()
    assert session["status"] == "DRAFT"
    assert session["store_name"] == "SM Supermarket"
    session_id = session["id"]

    # 2. Add an item while shopping/scanning
    item_res = client.post(
        f"/api/v1/grocery-sessions/{session_id}/add-item",
        json={
            "product_id": p1["id"],
            "storage_location_id": loc["id"],
            "quantity": 2.0,
            "unit_price": 140.0,
            "expiration_date": (date.today() + timedelta(days=14)).isoformat(),
        },
    )
    assert item_res.status_code == 201
    assert item_res.json()["remaining_quantity"] == 2.0

    # 3. Commit session with second item scanned at checkout
    commit_res = client.post(
        f"/api/v1/grocery-sessions/{session_id}/commit",
        json={
            "items": [
                {
                    "product_id": p2["id"],
                    "storage_location_id": loc["id"],
                    "quantity": 1.0,
                    "unit_price": 85.0,
                    "expiration_date": (date.today() + timedelta(days=7)).isoformat(),
                }
            ],
            "total_amount": 365.0,
        },
    )
    assert commit_res.status_code == 200
    committed = commit_res.json()
    assert committed["status"] == "COMPLETED"
    assert committed["total_amount"] == 365.0
    assert len(committed["batches"]) == 2

    # 4. Attempting to add item to completed session should fail
    fail_res = client.post(
        f"/api/v1/grocery-sessions/{session_id}/add-item",
        json={"product_id": p1["id"], "quantity": 1.0},
    )
    assert fail_res.status_code == 400


def test_cancel_grocery_session(client):
    session = client.post("/api/v1/grocery-sessions/", json={"store_name": "Target"}).json()
    session_id = session["id"]

    del_res = client.delete(f"/api/v1/grocery-sessions/{session_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "CANCELLED"
