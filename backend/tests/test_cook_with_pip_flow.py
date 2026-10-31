"""One seeded household across recommendation, discovery, and shopping flows."""

from decimal import Decimal

from sqlalchemy import func, select

from app.api.v1.endpoints.ai_recipes import get_provider
from app.main import app
from app.models.batch import InventoryBatch
from app.models.shopping import ShoppingListItem
from test_deepseek_discovery import FakeSearchProvider, _add_source, _grant, _search_result
from test_recipe_shopping import add_pantry, confirm_payload, make_recipe, ready_profiles, setup_ingredient


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
