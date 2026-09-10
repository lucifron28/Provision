from datetime import date, timedelta
from decimal import Decimal

def test_create_and_list_batches(client):
    # 1. Setup product and location
    p_res = client.post("/api/v1/products/", json={"name": "Century Tuna", "brand": "Century"})
    product_id = p_res.json()["id"]

    loc_res = client.post("/api/v1/locations/", json={"name": "Pantry"})
    location_id = loc_res.json()["id"]

    # 2. Create Batch A (expires in 10 days)
    exp_a = (date.today() + timedelta(days=10)).isoformat()
    batch_a_payload = {
        "product_id": product_id,
        "storage_location_id": location_id,
        "original_quantity": 6.0,
        "unit_price": 42.0,
        "expiration_date": exp_a,
    }
    b1_res = client.post("/api/v1/batches/", json=batch_a_payload)
    assert b1_res.status_code == 201
    b1 = b1_res.json()
    assert b1["remaining_quantity"] == 6.0
    assert Decimal(str(b1["unit_price"])) == Decimal("42.00")
    assert b1["product"]["id"] == product_id

    # 3. Create Batch B (expires in 5 days - should come first in FEFO!)
    exp_b = (date.today() + timedelta(days=5)).isoformat()
    batch_b_payload = {
        "product_id": product_id,
        "storage_location_id": location_id,
        "original_quantity": 12.0,
        "unit_price": 45.5,
        "expiration_date": exp_b,
    }
    b2_res = client.post("/api/v1/batches/", json=batch_b_payload)
    assert b2_res.status_code == 201

    # 4. List batches - check FEFO order
    list_res = client.get(f"/api/v1/batches/?product_id={product_id}")
    assert list_res.status_code == 200
    batches = list_res.json()
    assert len(batches) == 2
    # Batch B (exp_b, in 5 days) must come BEFORE Batch A (exp_a, in 10 days)
    assert batches[0]["expiration_date"] == exp_b
    assert batches[1]["expiration_date"] == exp_a

    # 5. Check product stock aggregation
    prod_check = client.get(f"/api/v1/products/{product_id}")
    assert prod_check.status_code == 200
    prod_data = prod_check.json()
    assert prod_data["total_remaining_quantity"] == 18.0
    assert prod_data["active_batches_count"] == 2


def test_batch_update_metadata_and_delete_protection(client):
    p_res = client.post("/api/v1/products/", json={"name": "Oatmeal"})
    product_id = p_res.json()["id"]

    b_res = client.post(
        "/api/v1/batches/",
        json={"product_id": product_id, "original_quantity": 5.0, "unit_price": 80.0},
    )
    batch_id = b_res.json()["id"]

    # 1. Test that PATCH updates metadata (e.g. unit_price)
    patch_res = client.patch(f"/api/v1/batches/{batch_id}", json={"unit_price": 85.0})
    assert patch_res.status_code == 200
    assert Decimal(str(patch_res.json()["unit_price"])) == Decimal("85.00")

    # 2. Invariant 6: Test that PATCH cannot directly change remaining_quantity
    patch_qty_res = client.patch(f"/api/v1/batches/{batch_id}", json={"remaining_quantity": 1.0})
    assert patch_qty_res.status_code == 200
    assert patch_qty_res.json()["remaining_quantity"] == 5.0  # Must NOT change!

    # 3. Invariant 8: Batch with inventory events cannot be deleted (must return 409 Conflict)
    del_res = client.delete(f"/api/v1/batches/{batch_id}")
    assert del_res.status_code == 409
    assert "associated inventory event" in del_res.json()["detail"]
