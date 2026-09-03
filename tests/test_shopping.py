def test_shopping_list_crud_and_toggle(client):
    # 1. Manual item creation
    res1 = client.post(
        "/api/v1/shopping-list/",
        json={"name": "Paper Towels", "quantity": 2.0, "unit": "rolls"},
    )
    assert res1.status_code == 201
    item1 = res1.json()
    assert item1["name"] == "Paper Towels"
    assert item1["is_bought"] is False
    item1_id = item1["id"]

    # 2. Toggle bought status
    tog_res = client.post(f"/api/v1/shopping-list/{item1_id}/toggle")
    assert tog_res.status_code == 200
    assert tog_res.json()["is_bought"] is True

    # 3. Create item from existing product
    prod = client.post(
        "/api/v1/products/",
        json={"name": "Olive Oil", "brand": "Bertolli", "unit": "bottle"},
    ).json()

    res2 = client.post(
        "/api/v1/shopping-list/",
        json={"product_id": prod["id"], "quantity": 1.0},
    )
    assert res2.status_code == 201
    item2 = res2.json()
    assert item2["name"] == "Olive Oil"
    assert item2["unit"] == "bottle"
    assert item2["product"]["id"] == prod["id"]

    # 4. List items (filter unbought)
    list_unbought = client.get("/api/v1/shopping-list/?is_bought=false")
    assert list_unbought.status_code == 200
    assert len(list_unbought.json()) == 1
    assert list_unbought.json()[0]["name"] == "Olive Oil"

    # 5. Clear completed
    clear_res = client.delete("/api/v1/shopping-list/completed/clear")
    assert clear_res.status_code == 200
    assert "1 completed item" in clear_res.json()["message"]


def test_generate_from_low_stock(client):
    # Create product with 0 stock
    prod = client.post(
        "/api/v1/products/",
        json={"name": "Eggs", "unit": "dozen"},
    ).json()

    # Trigger auto-generate with default threshold = 1.0
    gen_res = client.post(
        "/api/v1/shopping-list/generate-from-low-stock",
        json={"threshold": 1.0},
    )
    assert gen_res.status_code == 200
    items = gen_res.json()
    assert len(items) >= 1
    egg_item = next(i for i in items if i["name"] == "Eggs")
    assert egg_item["product_id"] == prod["id"]

    # Second run shouldn't duplicate the item
    gen_res2 = client.post(
        "/api/v1/shopping-list/generate-from-low-stock",
        json={"threshold": 1.0},
    )
    assert gen_res2.status_code == 200
    assert len(gen_res2.json()) == 0
