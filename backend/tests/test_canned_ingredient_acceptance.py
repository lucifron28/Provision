from decimal import Decimal
from datetime import timedelta

from app.core.time import household_today
from app.services.ingredient_matching import seed_ingredient_catalog_v1


def _tomato_ingredient_id(client, db):
    seed_ingredient_catalog_v1(db)
    db.commit()
    response = client.get("/api/v1/ingredients/?query=kamatis")
    assert response.status_code == 200, response.text
    matches = response.json()["results"]
    assert len(matches) == 1
    assert matches[0]["canonical_name"] == "tomato"
    return matches[0]["id"]


def _availability(client, ingredient_id, grams):
    response = client.post(
        "/api/v1/ingredients/availability",
        json={
            "recipe_servings": "1",
            "servings": "1",
            "requirements": [
                {"ingredient_id": ingredient_id, "amount": str(grams), "unit": "g"}
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["requirements"][0]


def test_verified_canned_goods_factor_counts_exact_ingredient_quantity(
    client, db
):
    ingredient_id = _tomato_ingredient_id(client, db)
    product_response = client.post(
        "/api/v1/products/",
        json={"name": "Synthetic canned tomatoes", "brand": "Test fixture", "unit": "can"},
    )
    assert product_response.status_code == 201, product_response.text
    product_id = product_response.json()["id"]

    mapping = client.put(
        f"/api/v1/ingredients/products/{product_id}/mapping",
        json={
            "mode": "DIRECT",
            "ingredient_id": ingredient_id,
            "verified": True,
            "method": "Synthetic can label review",
            "unknown_composition": False,
            "package_factors": [
                {
                    "ingredient_id": ingredient_id,
                    "inventory_unit": "can",
                    "ingredient_amount": "400",
                    "ingredient_unit": "g",
                    "source_reference": "Synthetic label states 400 g tomatoes per can",
                }
            ],
        },
    )
    assert mapping.status_code == 200, mapping.text
    assert mapping.json()["verification_status"] == "VERIFIED"

    batch = client.post(
        "/api/v1/batches/",
        json={
            "product_id": product_id,
            "original_quantity": "2.5",
            "expiration_date": (household_today() + timedelta(days=30)).isoformat(),
        },
    )
    assert batch.status_code == 201, batch.text

    line = _availability(client, ingredient_id, 900)
    assert line["status"] == "full"
    assert Decimal(line["required_amount"]) == Decimal("900")
    assert Decimal(line["available_amount"]) == Decimal("1000")
    assert Decimal(line["shortfall"]) == 0


def test_canned_goods_with_unknown_composition_never_contribute_stock(
    client, db
):
    ingredient_id = _tomato_ingredient_id(client, db)
    product_response = client.post(
        "/api/v1/products/",
        json={"name": "Synthetic canned meal, contents unknown", "unit": "can"},
    )
    assert product_response.status_code == 201, product_response.text
    product_id = product_response.json()["id"]

    mapping = client.put(
        f"/api/v1/ingredients/products/{product_id}/mapping",
        json={
            "mode": "DIRECT",
            "ingredient_id": ingredient_id,
            "verified": True,
            "method": "Identity only; contents not reviewed",
            "unknown_composition": True,
        },
    )
    assert mapping.status_code == 200, mapping.text
    assert mapping.json()["unknown_composition"] is True

    batch = client.post(
        "/api/v1/batches/",
        json={
            "product_id": product_id,
            "original_quantity": "3",
            "expiration_date": (household_today() + timedelta(days=30)).isoformat(),
        },
    )
    assert batch.status_code == 201, batch.text

    line = _availability(client, ingredient_id, 300)
    assert line["status"] == "unknown"
    assert Decimal(line["required_amount"]) == Decimal("300")
    assert Decimal(line["available_amount"]) == Decimal("0")
    assert line["shortfall"] is None
    assert "composition_unknown" in line["unknown_reasons"]
