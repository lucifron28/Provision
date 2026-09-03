from datetime import date, timedelta
from decimal import Decimal

def test_analytics_endpoints(client):
    # 1. Setup products and locations
    p1 = client.post(
        "/api/v1/products/",
        json={"name": "Century Tuna", "brand": "Century", "unit": "cans"},
    ).json()
    p2 = client.post(
        "/api/v1/products/",
        json={"name": "Fresh Milk", "brand": "Cowhead", "unit": "liters"},
    ).json()
    loc = client.post("/api/v1/locations/", json={"name": "Pantry"}).json()

    # 2. Add batches
    exp_soon = (date.today() + timedelta(days=3)).isoformat()
    exp_later = (date.today() + timedelta(days=30)).isoformat()

    # Batch 1: Tuna, 10 cans @ 40 each, expires in 30 days
    client.post(
        "/api/v1/batches/",
        json={
            "product_id": p1["id"],
            "storage_location_id": loc["id"],
            "original_quantity": 10.0,
            "unit_price": 40.0,
            "expiration_date": exp_later,
        },
    )

    # Batch 2: Tuna, 2 cans @ 45 each (price increase!), expires in 3 days (expiring soon)
    b2 = client.post(
        "/api/v1/batches/",
        json={
            "product_id": p1["id"],
            "storage_location_id": loc["id"],
            "original_quantity": 2.0,
            "unit_price": 45.0,
            "expiration_date": exp_soon,
        },
    ).json()

    # Test Inventory Summary: "What food do I own? How much remains? Where is it stored?"
    inv_res = client.get("/api/v1/analytics/inventory-summary")
    assert inv_res.status_code == 200
    summary = inv_res.json()
    assert len(summary) == 1
    tuna_summary = summary[0]
    assert tuna_summary["product_name"] == "Century Tuna"
    assert tuna_summary["total_remaining"] == 12.0
    assert tuna_summary["active_batches_count"] == 2
    assert "Pantry" in tuna_summary["locations"]

    # Test Expiring Soon: "What is expiring soon? Which items should I use first?"
    exp_res = client.get("/api/v1/analytics/expiring-soon?days=7")
    assert exp_res.status_code == 200
    expiring = exp_res.json()
    assert len(expiring) == 1
    assert expiring[0]["batch_id"] == b2["id"]
    assert expiring[0]["days_until_expiration"] == 3

    # Test Low Stock: "What am I running low on?"
    # Milk has 0 stock -> should appear in low-stock
    low_res = client.get("/api/v1/analytics/low-stock?threshold=1.0")
    assert low_res.status_code == 200
    low_stock = low_res.json()
    assert any(item["product_id"] == p2["id"] for item in low_stock)

    # Test Inventory Valuation: "How much is my food worth?"
    # (10 * 40) + (2 * 45) = 400 + 90 = 490
    val_res = client.get("/api/v1/analytics/valuation")
    assert val_res.status_code == 200
    val_data = val_res.json()
    assert Decimal(str(val_data["total_value"])) == Decimal("490.00")
    assert val_data["total_active_batches"] == 2

    # Test Price History: "How have prices changed over time?"
    price_res = client.get(f"/api/v1/analytics/price-history/{p1['id']}")
    assert price_res.status_code == 200
    price_data = price_res.json()
    assert len(price_data["price_points"]) == 2
    prices = [Decimal(str(pt["unit_price"])) for pt in price_data["price_points"]]
    assert Decimal("40.00") in prices
    assert Decimal("45.00") in prices

    # Test Waste Tracking: discard b2 (2 cans @ 45)
    client.post(
        f"/api/v1/inventory/batches/{b2['id']}/discard",
        json={"reason": "Dented can"},
    )
    waste_res = client.get("/api/v1/analytics/waste")
    assert waste_res.status_code == 200
    waste_data = waste_res.json()
    assert waste_data["total_waste_events"] == 1
    assert waste_data["total_quantity_wasted"] == 2.0
    assert Decimal(str(waste_data["total_financial_loss"])) == Decimal("90.00")  # 2 cans * 45.0 = 90.00
