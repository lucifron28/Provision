"""One seeded household across recommendation, discovery, and shopping flows."""

from decimal import Decimal

from sqlalchemy import func, select

from app.api.v1.endpoints.ai_recipes import get_provider
from app.api.v1.endpoints.recipe_sources import get_mealdb_budget, get_mealdb_client
from app.main import app
from app.models.batch import InventoryBatch
from app.models.shopping import ShoppingListItem
from test_deepseek_discovery import FakeSearchProvider, _add_source, _grant, _search_result
from test_recipe_shopping import add_pantry, confirm_payload, make_recipe, ready_profiles, setup_ingredient
from test_themealdb_assessment import record, setup_sources
from test_themealdb_reviewed import Budget, Client


def test_seeded_household_recommend_discover_and_confirm_shopping(
    client, db, auth_user, auth_household
):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    enough = make_recipe(db, auth_household, auth_user, ingredient, amount=2)
    almost = make_recipe(db, auth_household, auth_user, ingredient, amount=10)
    _, batch = add_pantry(db, auth_household, auth_user, ingredient, 8)
    _grant(db, auth_user, auth_household)
    host = "priority.publisher.example.com"
    _add_source(db, host)
    db.commit()
    provider = FakeSearchProvider({host: [_search_result(f"https://{host}/recipe/adobo")]})
    app.dependency_overrides[get_provider] = lambda: provider

    ready = client.post("/api/v1/recipes/recommendations", json={"mode": "cook_now"})
    assert ready.status_code == 200
    assert enough.id in [item["recipe"]["id"] for item in ready.json()["items"]]
    nearly = client.post("/api/v1/recipes/recommendations", json={"mode": "almost_there"})
    assert nearly.status_code == 200
    assert almost.id in [item["recipe"]["id"] for item in nearly.json()["items"]]

    discovery = client.post("/api/v1/recipe-sources/discover", json={"query": "adobo"})
    assert discovery.status_code == 200
    assert discovery.json()["results"][0]["canonical_url"] == f"https://{host}/recipe/adobo"

    preview = client.post("/api/v1/recipe-shopping/preview", json={
        "recipe_id": almost.id, "expected_recipe_revision": almost.revision,
        "servings": "1", "include_optional": False,
    })
    assert preview.status_code == 200, preview.text
    assert Decimal(preview.json()["lines"][0]["shortage"]) == 2
    db.expire_all()
    assert db.get(InventoryBatch, batch.id).remaining_quantity == Decimal("8")
    assert db.scalar(select(func.count()).select_from(ShoppingListItem)) == 0

    payload = confirm_payload(
        preview.json(), ingredient.id, "2", key="seeded-flow-confirmation"
    )
    confirmation = client.post("/api/v1/recipe-shopping/confirm", json=payload)
    assert confirmation.status_code == 200, confirmation.text
    assert len(confirmation.json()["created"]) == 1
    replay = client.post("/api/v1/recipe-shopping/confirm", json=payload)
    assert replay.status_code == 200, replay.text
    assert replay.json() == confirmation.json()
    db.expire_all()
    assert db.get(InventoryBatch, batch.id).remaining_quantity == Decimal("8")
    assert db.scalar(select(func.count()).select_from(ShoppingListItem)) == 1


def test_reviewed_source_to_user_confirmed_shopping(client, db, auth_user, auth_household):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    _, batch = add_pantry(db, auth_household, auth_user, ingredient, 8)
    setup_sources(db, auth_user, auth_household)
    app.dependency_overrides[get_mealdb_client] = lambda: Client(record("to taste"))
    app.dependency_overrides[get_mealdb_budget] = lambda: Budget()

    preview = client.post("/api/v1/recipe-sources/mealdb/123/preview", json={})
    assert preview.status_code == 200, preview.text
    source = preview.json()["source"]
    assessment = client.post("/api/v1/recipe-sources/mealdb/123/assess", json={
        "source_digest": source["content_digest"], "confirmed_recipe_servings": 1,
        "requested_servings": 1,
        "confirmed_measures": [{"ingredient_index": 0, "amount": "10", "unit": "g"}],
    })
    assert assessment.status_code == 200, assessment.text
    assert assessment.json()["safety"]["decision"] == "review_required"
    assert db.scalar(select(func.count()).select_from(ShoppingListItem)) == 0

    # The user separately enters and saves the reviewed recipe and source link.
    saved = client.post("/api/v1/recipes/", json={
        "title": source["title"], "cuisine": "Filipino", "ph_regions": ["region_unknown"],
        "content_permission": "OWNED_OR_PERMISSION_GRANTED", "servings": 1,
        "instructions": [source["instructions"]],
        "ingredients": [{"ingredient_id": ingredient.id, "amount": "10", "unit": "g"}],
    })
    assert saved.status_code == 201, saved.text
    recipe = saved.json()
    linked = client.put(f"/api/v1/recipe-sources/recipes/{recipe['id']}/reference", json={
        "expected_revision": None, "expected_recipe_revision": recipe["revision"],
        "url": source["source_url"], "author": None, "allow_broader_web": False,
    })
    assert linked.status_code == 200, linked.text
    assert linked.json()["canonical_url"] == source["source_url"]

    shopping = client.post("/api/v1/recipe-shopping/preview", json={
        "recipe_id": recipe["id"], "expected_recipe_revision": recipe["revision"],
        "servings": "1", "include_optional": False,
    })
    assert shopping.status_code == 200, shopping.text
    assert Decimal(shopping.json()["lines"][0]["shortage"]) == 2
    db.expire_all()
    assert db.get(InventoryBatch, batch.id).remaining_quantity == Decimal("8")
    assert db.scalar(select(func.count()).select_from(ShoppingListItem)) == 0

    payload = confirm_payload(shopping.json(), ingredient.id, "2", key="reviewed-source-confirmation")
    confirmed = client.post("/api/v1/recipe-shopping/confirm", json=payload)
    assert confirmed.status_code == 200, confirmed.text
    assert len(confirmed.json()["created"]) == 1
    assert client.post("/api/v1/recipe-shopping/confirm", json=payload).json() == confirmed.json()
    db.expire_all()
    assert db.get(InventoryBatch, batch.id).remaining_quantity == Decimal("8")
    assert db.scalar(select(func.count()).select_from(ShoppingListItem)) == 1
