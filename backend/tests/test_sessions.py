from datetime import date, timedelta
from decimal import Decimal


def test_grocery_session_full_flow(client):
    # Setup products and location
    p1 = client.post("/api/v1/products/", json={"name": "Almond Milk", "brand": "Silk"}).json()
    p2 = client.post("/api/v1/products/", json={"name": "Whole Wheat Bread", "brand": "Gardenia"}).json()
    loc = client.post("/api/v1/locations/", json={"name": "Kitchen Counter"}).json()

    # 1. Invariant 1: Start Session (must be DRAFT, and must NOT affect inventory)
    session_res = client.post(
        "/api/v1/grocery-sessions/",
        json={"store_name": "SM Supermarket", "notes": "Weekly grocery intake"},
    )
    assert session_res.status_code == 201
    session = session_res.json()
    assert session["status"] == "DRAFT"
    assert session["store_name"] == "SM Supermarket"
    session_id = session["id"]

    # Verify 0 inventory batches exist for these products
    b_check1 = client.get(f"/api/v1/batches/?product_id={p1['id']}")
    assert len(b_check1.json()) == 0
    b_check2 = client.get(f"/api/v1/batches/?product_id={p2['id']}")
    assert len(b_check2.json()) == 0

    # 2. Invariant 3: Commit finalized intake list creates batches and PURCHASED events once
    commit_payload = {
        "items": [
            {
                "product_id": p1["id"],
                "storage_location_id": loc["id"],
                "quantity": 2.0,
                "unit_price": 140.0,
                "expiration_date": (date.today() + timedelta(days=14)).isoformat(),
            },
            {
                "product_id": p2["id"],
                "storage_location_id": loc["id"],
                "quantity": 1.0,
                "unit_price": 85.0,
                "expiration_date": (date.today() + timedelta(days=7)).isoformat(),
            },
        ],
        "total_amount": 365.0,
    }
    commit_res = client.post(f"/api/v1/grocery-sessions/{session_id}/commit", json=commit_payload)
    assert commit_res.status_code == 200
    committed = commit_res.json()
    assert committed["status"] == "COMPLETED"
    assert Decimal(str(committed["total_amount"])) == Decimal("365.00")
    assert len(committed["batches"]) == 2

    # Verify inventory batches and events exist
    b_after1 = client.get(f"/api/v1/batches/?product_id={p1['id']}").json()
    assert len(b_after1) == 1
    assert b_after1[0]["remaining_quantity"] == 2.0
    assert Decimal(str(b_after1[0]["unit_price"])) == Decimal("140.00")

    # Invariant 4: Commit cannot be repeated on an already completed session
    recommit_res = client.post(f"/api/v1/grocery-sessions/{session_id}/commit", json=commit_payload)
    assert recommit_res.status_code == 400
    assert "already completed" in recommit_res.json()["detail"].lower()

    # Invariant 9 (part): Completed session cannot be cancelled
    del_completed_res = client.delete(f"/api/v1/grocery-sessions/{session_id}")
    assert del_completed_res.status_code == 400
    assert "already completed" in del_completed_res.json()["detail"].lower()


def test_cancel_grocery_session(client):
    p = client.post("/api/v1/products/", json={"name": "Coffee Beans"}).json()

    # 1. Start draft session
    session = client.post("/api/v1/grocery-sessions/", json={"store_name": "Target"}).json()
    session_id = session["id"]

    # 2. Invariant 2: Cancelling a draft session leaves inventory completely empty
    del_res = client.delete(f"/api/v1/grocery-sessions/{session_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "CANCELLED"

    # Confirm no inventory batches were created
    batches = client.get(f"/api/v1/batches/?product_id={p['id']}").json()
    assert len(batches) == 0

    # Invariant 5: Cancelled session cannot be committed
    commit_res = client.post(
        f"/api/v1/grocery-sessions/{session_id}/commit",
        json={"items": [{"product_id": p["id"], "quantity": 1.0}]},
    )
    assert commit_res.status_code == 400
    assert "cancelled session" in commit_res.json()["detail"].lower()
