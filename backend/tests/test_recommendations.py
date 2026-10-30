from datetime import timedelta
from decimal import Decimal

from app.core.time import household_today
from app.models.batch import InventoryBatch
from app.models.recipe import Recipe
from sqlalchemy import select
from test_food_safety import catalog, declare
from test_product_labels import label_payload, stock
from test_recipes import create


def recommend(client, **kwargs):
    response = client.post("/api/v1/recipes/recommendations", json=kwargs)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_recommendations_apply_safety_before_ranking_and_load_server_ingredients(client, catalog):
    declare(client, "egg")
    create(client, title="Fast egg dish", cook_minutes=0, prep_minutes=0,
        ingredients=[dict(display_name="egg", amount=1, unit="count")])
    allowed = create(client, title="Garlic dish", ingredients=[dict(display_name="garlic", amount=1, unit="g")])
    result = recommend(client)
    assert [item["recipe"]["id"] for item in result["items"]] == [allowed["id"]]
    assert result["excluded_blocked"] == 1 and result["provider_enabled"] is False
    assert result == recommend(client)
    assert recommend(client, mode="cook_now")["items"] == []
    almost = recommend(client, mode="almost_there")
    assert almost["items"][0]["missing_ingredient_count"] == 1


def test_cook_now_requires_current_labels_and_ranks_usable_expiry(client, db, catalog):
    declare(client)
    rice, _ = stock(client, catalog, name="rice")
    garlic, _ = stock(client, catalog, name="garlic")
    for product in (rice, garlic):
        response = client.put(f"/api/v1/food-safety/products/{product['id']}/label", json=label_payload(product))
        assert response.status_code == 200
    for product, days in [(rice, 1), (garlic, 20)]:
        batch = db.scalar(select(InventoryBatch).where(InventoryBatch.product_id == product["id"]))
        batch.expiration_date = household_today() + timedelta(days=days)
    db.commit()
    near = create(client, title="Z rice", ingredients=[dict(display_name="rice", amount=1, unit="g")])
    create(client, title="A garlic", ingredients=[dict(display_name="garlic", amount=1, unit="g")])
    result = recommend(client, mode="cook_now", servings=2)
    assert len(result["items"]) == 2 and result["items"][0]["recipe"]["id"] == near["id"]
    assert Decimal(result["items"][0]["coverage"]) == 1
    assert result["items"][0]["near_expiry_batch_count"] == 1
    assert client.delete(f"/api/v1/food-safety/products/{rice['id']}/label?expected_revision=1").status_code == 204
    assert len(recommend(client, mode="cook_now")["items"]) == 1


def test_recommendation_filters_and_unknown_quantities(client, catalog):
    declare(client)
    create(client, title="Slow Bicol meal", ph_regions=["Bicolano"], prep_minutes=10, cook_minutes=60,
        equipment=["pot"], ingredients=[dict(display_name="garlic", amount=1, unit="g")])
    quick = create(client, title="Fast meal", prep_minutes=0, cook_minutes=5,
        ingredients=[dict(display_name="onion", amount=1, unit="g")])
    create(client, title="Unknown cups", ingredients=[dict(display_name="garlic", amount=1, unit="cup")])
    assert recommend(client)["excluded_unknown_quantities"] == 1
    assert [item["recipe"]["id"] for item in recommend(client, max_total_minutes=10)["items"]] == [quick["id"]]
    assert len(recommend(client, ph_region="Bicolano", available_equipment=["pot"])["items"]) == 1
    assert recommend(client, ph_region="Bicolano", available_equipment=[])["items"] == []
    assert recommend(client, cuisine="Filipino%")["items"] == []
    assert recommend(client, priority="quick")["items"][0]["recipe"]["id"] == quick["id"]


def test_missing_allergy_profile_excludes_candidates_and_foreign_diners_rejected_even_when_empty(client, catalog):
    create(client, ingredients=[dict(display_name="garlic", amount=1, unit="g")])
    result = recommend(client)
    assert result["items"] == [] and result["excluded_review_required"] == 1
    denied = client.post("/api/v1/recipes/recommendations", json=dict(query="no matches", diner_user_ids=[999999]))
    assert denied.status_code == 403


def test_candidate_window_and_household_scope_are_explicit(client, db, catalog, auth_household):
    declare(client)
    first = create(client, title="First", ingredients=[dict(display_name="garlic", amount=1, unit="g")])
    second = create(client, title="Second", ingredients=[dict(display_name="garlic", amount=1, unit="g")])
    result = recommend(client, candidate_limit=1)
    assert result["has_more_candidates"] is True and result["candidates_evaluated"] == 1
    assert result["items"][0]["recipe"]["id"] == first["id"]
    assert recommend(client, candidate_limit=1, candidate_offset=1)["items"][0]["recipe"]["id"] == second["id"]
