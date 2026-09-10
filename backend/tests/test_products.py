def test_create_and_get_product(client):
    payload = {
        "name": "Century Tuna Flakes in Oil",
        "brand": "Century",
        "barcode": "4800123456789",
        "category": "Canned Goods",
        "package_size": 180.0,
        "unit": "g",
        "source": "USER_CONFIRMED",
    }
    res = client.post("/api/v1/products/", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == payload["name"]
    assert data["barcode"] == payload["barcode"]
    assert data["total_remaining_quantity"] == 0.0
    product_id = data["id"]

    # Barcode lookup
    res_bc = client.get(f"/api/v1/products/barcode/{payload['barcode']}")
    assert res_bc.status_code == 200
    assert res_bc.json()["id"] == product_id

    # Duplicate barcode rejection
    res_dup = client.post("/api/v1/products/", json=payload)
    assert res_dup.status_code == 400

    # Get by ID
    res_get = client.get(f"/api/v1/products/{product_id}")
    assert res_get.status_code == 200
    assert res_get.json()["brand"] == "Century"


def test_list_products_filtering(client):
    client.post("/api/v1/products/", json={"name": "Fresh Milk", "brand": "Cowhead", "category": "Dairy"})
    client.post("/api/v1/products/", json={"name": "Oat Milk", "brand": "Oatly", "category": "Dairy"})
    client.post("/api/v1/products/", json={"name": "Jasmine Rice", "brand": "Doña Maria", "category": "Grains"})

    # Search filter
    res = client.get("/api/v1/products/?search=Milk")
    assert res.status_code == 200
    assert len(res.json()) == 2

    # Category filter
    res_cat = client.get("/api/v1/products/?category=Grains")
    assert res_cat.status_code == 200
    assert len(res_cat.json()) == 1
    assert res_cat.json()[0]["name"] == "Jasmine Rice"
