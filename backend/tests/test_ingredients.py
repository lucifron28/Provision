from sqlalchemy import func, select

from app.models.ingredient import ProductIngredientMapping
from app.models.household import Household
from app.models.product import Product
from app.services.ingredient_matching import seed_ingredient_catalog_v1


def test_mapping_api_version_scope_and_readonly_availability(client, db, auth_household):
    seed_ingredient_catalog_v1(db)
    db.commit()
    ingredient = client.get("/api/v1/ingredients/?query=itlog").json()["results"][0]
    assert client.get("/api/v1/ingredients/?query=bagoong").json()["ambiguous"] is True
    product = client.post("/api/v1/products/", json={"name": "Egg carton", "unit": "carton"}).json()
    url = f"/api/v1/ingredients/products/{product['id']}/mapping"
    payload = dict(mode="DIRECT", ingredient_id=ingredient["id"], verified=True,
        unknown_composition=False, method="Reviewed label", package_factors=[dict(
            ingredient_id=ingredient["id"], inventory_unit="carton", ingredient_amount="12",
            ingredient_unit="count", source_reference="Carton label: 12 eggs")])
    created = client.put(url, json=payload)
    assert created.status_code == 200, created.text
    assert created.json()["version"] == 1
    assert client.put(url, json=payload).status_code == 409
    client.post("/api/v1/batches/", json={"product_id": product["id"], "original_quantity": 1})
    preview = dict(recipe_servings=1, servings=1, requirements=[dict(ingredient_id=ingredient["id"], amount=4, unit="count")])
    result = client.post("/api/v1/ingredients/availability", json=preview)
    assert result.status_code == 200, result.text
    assert result.json()["requirements"][0]["available_amount"] == "12.00000000"
    assert result.json()["overall_status"] == "full"
    assert client.get(url).json()["version"] == 1
    assert db.scalar(select(func.count()).select_from(ProductIngredientMapping)) == 1
    other = Household(name="Other", slug="other")
    db.add(other)
    db.flush()
    foreign = Product(name="Private", household_id=other.id)
    db.add(foreign)
    db.commit()
    foreign_url = f"/api/v1/ingredients/products/{foreign.id}/mapping"
    assert client.get(foreign_url).status_code == 404
    assert client.put(foreign_url, json=payload).status_code == 404


def test_ingredient_api_requires_authentication(unauthed_client):
    assert unauthed_client.get("/api/v1/ingredients/").status_code == 401
