from sqlalchemy import func, select
from sqlalchemy.orm import Session
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from fastapi import HTTPException

from app.api.v1.endpoints.ingredients import put_mapping
from app.models.user import User
from app.schemas.ingredients import ProductIngredientMappingUpsert

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


def test_concurrent_mapping_creation_accepts_exactly_one_writer(client, db, engine, auth_household, auth_user):
    seed_ingredient_catalog_v1(db)
    db.commit()
    ingredient_id = client.get("/api/v1/ingredients/?query=itlog").json()["results"][0]["id"]
    product_id = client.post("/api/v1/products/", json={"name": "Egg", "unit": "count"}).json()["id"]
    household_id, user_id = auth_household.id, auth_user.id
    db.rollback()
    barrier = Barrier(2)
    payload = ProductIngredientMappingUpsert(mode="DIRECT", ingredient_id=ingredient_id, method="manual")

    def write():
        with Session(engine) as independent:
            user = independent.get(User, user_id)
            barrier.wait(timeout=10)
            try:
                result = put_mapping(product_id, payload, household_id, user, independent)
                return result.version
            except HTTPException as exc:
                independent.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: write(), range(2)))
    assert sorted(results) == [1, 409]
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(ProductIngredientMapping)) == 1
