def test_create_and_list_locations(client):
    # Test create
    payload = {"name": "Refrigerator", "description": "Kitchen fridge top and bottom"}
    res = client.post("/api/v1/locations/", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Refrigerator"
    assert data["id"] is not None

    # Test duplicate prevention
    res_dup = client.post("/api/v1/locations/", json=payload)
    assert res_dup.status_code == 400

    # Test list
    res_list = client.get("/api/v1/locations/")
    assert res_list.status_code == 200
    locations = res_list.json()
    assert len(locations) == 1
    assert locations[0]["name"] == "Refrigerator"


def test_update_and_delete_location(client):
    res = client.post("/api/v1/locations/", json={"name": "Pantry Shelf 1"})
    loc_id = res.json()["id"]

    # Patch
    patch_res = client.patch(f"/api/v1/locations/{loc_id}", json={"description": "Dry goods"})
    assert patch_res.status_code == 200
    assert patch_res.json()["description"] == "Dry goods"

    # Delete
    del_res = client.delete(f"/api/v1/locations/{loc_id}")
    assert del_res.status_code == 204

    # Confirm 404
    get_res = client.get(f"/api/v1/locations/{loc_id}")
    assert get_res.status_code == 404
